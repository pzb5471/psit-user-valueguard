"""M1-03：标准 ZIP 的临时暂存与完整校验（技术实施规格 5.4/5.6/12.4；ADR-0033/0026/0067/0055）。

单 ZIP 两步导入的第一步：接收上传的 ZIP 字节流，在不写正式数据库的前提下完成
路径安全、Schema、校验值、媒体与答案泄漏检查，返回可业务化展示的逐项拒绝报告或
通过摘要（ADR-0026/0067：可预期拒绝不抛 Python 异常，意外异常保留技术因果链）。

接口不接受服务器文件路径、不返回临时绝对路径（规格 3.1）；临时暂存使用
runtime_data/imports/tmp/<uuid>/（ADR-0033），失败或成功后都立即清理，不恢复中断
临时目录。校验通过只表示"可导入"，正式发布为 PENDING_ANALYSIS 批次、包哈希幂等与
批次冲突属 M1-04 BatchImportGateway 职责（规格 5.4 导入规则；M1-03 禁止事项）。
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import shutil
import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO
from uuid import uuid4

from pydantic import ValidationError

from app.contracts.data import (
    BatchManifest,
    CaseInput,
    Checksums,
    ImageEvidenceItem,
    ImageMediaType,
    PackageType,
)

from .errors import ImportRejectionCode, ImportStage, RejectionInfo

# 上传大小上限占位默认值：正式冻结值由 M1-09 按 ADR-0055 写入 upload.max_zip_bytes，
# 本阶段保留 UPLOAD_TOO_LARGE 编号并提供可参数化上限，不臆造未经数据支持的常数。
DEFAULT_MAX_ZIP_BYTES = 256 * 1024 * 1024

# 临时暂存根：runtime_data/imports/tmp/（ADR-0033；runtime_data/ 不入 Git）。
DEFAULT_TMP_ROOT = Path(__file__).resolve().parents[5] / "runtime_data" / "imports" / "tmp"

_IMAGE_EXTENSION_TO_MEDIA_TYPE: dict[str, ImageMediaType] = {
    ".jpg": ImageMediaType.JPEG,
    ".jpeg": ImageMediaType.JPEG,
    ".png": ImageMediaType.PNG,
    ".gif": ImageMediaType.GIF,
}

_MEDIA_MAGIC: dict[ImageMediaType, tuple[bytes, ...]] = {
    ImageMediaType.JPEG: (b"\xff\xd8\xff",),
    ImageMediaType.PNG: (b"\x89PNG\r\n\x1a\n",),
    ImageMediaType.GIF: (b"GIF87a", b"GIF89a"),
}

_DRIVE_LETTER = re.compile(r"^[A-Za-z]:")

# URL 编码的 "."（2e）、"/"（2f）与 "\"（5c）：拒绝编码分隔符绕过。
_ENCODED_PATH_CHARS = re.compile(r"%(?:2e|2f|5c)", re.IGNORECASE)

# 规格 5.4 导入器必须递归拒绝的答案/答案性质字段。
_ANSWER_LEAK_KEYS = frozenset(
    {
        "mood",
        "reason",
        "solution",
        "image_verification",
        "key_answer",
        "label",
        "database_gt",
        "trajectory",
        "user_profile_st1",
        "user_profile",
        "question_type",
    }
)

# 未规范化即不得进入运行环境的内容字段（规格 5.4）。
_UNSANITIZED_KEYS = frozenset({"user_address", "database"})
_FIRST_QUERY_KEY = "first_query"
_PHONE_PATTERN = re.compile(r"1[3-9]\d{9}")
_URL_PATTERN = re.compile(r"https?://\S+", re.IGNORECASE)

_EXPECTED_TOP_LEVEL = frozenset({"manifest.json", "checksums.json"})
_REQUIRED_PREFIXES = ("cases/", "assets/")


def _first_validation_issue(exc: ValidationError, limit: int = 3) -> str:
    """把 Pydantic 校验错误压缩为字段定位 + 中文说明，不拼接客户正文。"""
    parts: list[str] = []
    for err in exc.errors()[:limit]:
        loc = ".".join(str(part) for part in err.get("loc", ()))
        parts.append(f"{loc}：{err.get('msg', '校验失败')}")
    return "；".join(parts) or "校验失败"


@dataclass(frozen=True, slots=True)
class _LeakFinding:
    message: str


def _scan_answer_leaks(
    node: object,
    findings: list[_LeakFinding],
    first_query_texts: list[str],
) -> None:
    """递归扫描 JSON 节点：答案泄漏字段、未脱敏字段与 first_query 文本。"""
    if isinstance(node, dict):
        for key, value in node.items():
            if key in _ANSWER_LEAK_KEYS:
                findings.append(_LeakFinding(f"检测到答案泄漏字段 {key}"))
            elif key in _UNSANITIZED_KEYS:
                findings.append(_LeakFinding(f"检测到未脱敏字段 {key}"))
            elif key == _FIRST_QUERY_KEY and isinstance(value, str):
                first_query_texts.append(value)
            _scan_answer_leaks(value, findings, first_query_texts)
    elif isinstance(node, list):
        for item in node:
            _scan_answer_leaks(item, findings, first_query_texts)


def _leak_findings(payload: dict) -> list[_LeakFinding]:
    findings: list[_LeakFinding] = []
    first_query_texts: list[str] = []
    _scan_answer_leaks(payload, findings, first_query_texts)
    if (
        len(first_query_texts) > 1
        and len(set(first_query_texts)) < len(first_query_texts)
    ):
        findings.append(_LeakFinding("检测到重复 first_query 文本"))
    return findings


def _text_privacy_findings(payload: dict) -> list[_LeakFinding]:
    """运行文本必须已脱敏；报告仅给字段位置，不回显客户正文。"""
    findings: list[_LeakFinding] = []
    evidence = payload.get("evidence")
    if not isinstance(evidence, dict):
        return findings
    items = evidence.get("text_items")
    if not isinstance(items, list):
        return findings
    for index, item in enumerate(items):
        if not isinstance(item, dict) or not isinstance(item.get("text"), str):
            continue
        text = item["text"]
        if _PHONE_PATTERN.search(text):
            findings.append(_LeakFinding(f"text_items[{index}].text 包含未脱敏手机号"))
        if _URL_PATTERN.search(text):
            findings.append(_LeakFinding(f"text_items[{index}].text 包含未脱敏 URL"))
    return findings


@dataclass(frozen=True, slots=True)
class StagePackageResult:
    """M1-03 单 ZIP 校验结果：通过摘要或逐项拒绝报告（规格 5.4/12.4）。

    拒绝时 rejections 非空，package_* 字段保持 None；通过时 package_* 给出
    导入摘要所需字段。报告不含本机路径与客户正文（M1-03 人工验收）。
    """

    ok: bool
    package_type: PackageType | None = None
    package_sha256: str | None = None
    case_count: int | None = None
    evidence_count: int | None = None
    is_mock: bool | None = None
    source_filename: str = ""
    rejections: tuple[RejectionInfo, ...] = ()


@dataclass(slots=True)
class _ParsedPackage:
    manifest: BatchManifest
    checksums: Checksums
    cases: list[tuple[str, CaseInput]]


class ZipImportStage:
    """标准 ZIP 的临时暂存与完整校验器（规格 5.4—5.6；ADR-0033/0055）。"""

    def __init__(
        self,
        *,
        tmp_root: Path | None = None,
        max_zip_bytes: int = DEFAULT_MAX_ZIP_BYTES,
    ) -> None:
        self.tmp_root = Path(tmp_root) if tmp_root is not None else DEFAULT_TMP_ROOT
        self.max_zip_bytes = max_zip_bytes

    def stage(
        self,
        source: bytes | BinaryIO,
        *,
        source_filename: str = "upload.zip",
    ) -> StagePackageResult:
        """校验单个 ZIP 字节流：返回通过摘要或逐项拒绝报告。"""
        if isinstance(source, bytes):
            raw = source
        else:
            raw = source.read()
        if not isinstance(raw, bytes):
            raise TypeError("ZIP 输入必须是 bytes 或二进制流")
        if len(raw) > self.max_zip_bytes:
            return StagePackageResult(
                ok=False,
                source_filename=source_filename,
                rejections=(
                    RejectionInfo(
                        code=ImportRejectionCode.UPLOAD_TOO_LARGE,
                        message=f"ZIP 超过上传大小上限（{self.max_zip_bytes} 字节）",
                        object_type="upload",
                        object_id=source_filename,
                        stage=ImportStage.ZIP_STRUCTURE,
                        next_action="裁剪或压缩案例后重新上传",
                    ),
                ),
            )

        package_sha256 = hashlib.sha256(raw).hexdigest()
        sandbox = self.tmp_root / uuid4().hex
        sandbox.mkdir(parents=True, exist_ok=True)
        rejections: list[RejectionInfo] = []
        parsed: _ParsedPackage | None = None
        try:
            file_entries = self._check_zip_structure(raw, sandbox, rejections)
            if file_entries is not None:
                parsed = self._check_manifest_and_cases(
                    sandbox, file_entries, rejections
                )
            if parsed is not None:
                assert file_entries is not None  # parsed 仅在 file_entries 非空时产生
                self._check_relationships_and_media(
                    sandbox, file_entries, parsed, rejections
                )
        finally:
            shutil.rmtree(sandbox, ignore_errors=True)

        rejections.sort(key=lambda r: (r.stage.value, r.object_id, r.code.value))
        if rejections:
            return StagePackageResult(
                ok=False,
                source_filename=source_filename,
                rejections=tuple(rejections),
            )
        # 无拒绝即代表结构/合同/关系全部通过，parsed 必然已生成。
        assert parsed is not None
        return StagePackageResult(
            ok=True,
            package_type=parsed.manifest.package_type,
            package_sha256=package_sha256,
            case_count=parsed.manifest.case_count,
            evidence_count=parsed.manifest.evidence_count,
            is_mock=parsed.manifest.is_mock,
            source_filename=source_filename,
        )

    def _reject(
        self,
        rejections: list[RejectionInfo],
        *,
        code: ImportRejectionCode,
        object_type: str,
        object_id: str,
        stage: ImportStage,
        message: str,
        next_action: str,
    ) -> None:
        rejections.append(
            RejectionInfo(
                code=code,
                message=message,
                object_type=object_type,
                object_id=object_id,
                stage=stage,
                next_action=next_action,
            )
        )

    # ---------- 第一步：ZIP 结构、路径安全与安全解压 ----------

    def _check_zip_structure(
        self,
        raw: bytes,
        sandbox: Path,
        rejections: list[RejectionInfo],
    ) -> dict[str, zipfile.ZipInfo] | None:
        try:
            archive = zipfile.ZipFile(io.BytesIO(raw))
        except zipfile.BadZipFile:
            self._reject(
                rejections,
                code=ImportRejectionCode.INVALID_ZIP,
                object_type="upload",
                object_id="upload.zip",
                stage=ImportStage.ZIP_STRUCTURE,
                message="无法解析 ZIP 文件",
                next_action="确认上传文件是有效 ZIP 后重新上传",
            )
            return None

        file_entries: dict[str, zipfile.ZipInfo] = {}
        seen: set[str] = set()
        with archive:
            for info in archive.infolist():
                kind = self._validate_entry(info, seen, rejections)
                if kind == "file":
                    file_entries[info.filename] = info
            if rejections:
                return None
            if "manifest.json" not in file_entries or "checksums.json" not in file_entries:
                self._reject(
                    rejections,
                    code=ImportRejectionCode.INVALID_ZIP,
                    object_type="package",
                    object_id="",
                    stage=ImportStage.ZIP_STRUCTURE,
                    message="标准 ZIP 必须包含 manifest.json 与 checksums.json",
                    next_action="按规格 5.4 补齐标准 ZIP 结构后重新上传",
                )
                return None
            if not any(name.startswith("cases/") for name in file_entries):
                self._reject(
                    rejections,
                    code=ImportRejectionCode.INVALID_ZIP,
                    object_type="package",
                    object_id="cases/",
                    stage=ImportStage.ZIP_STRUCTURE,
                    message="标准 ZIP 必须包含 cases/ 目录",
                    next_action="按规格 5.4 补齐案例目录后重新上传",
                )
                return None
            if not any(name.startswith("assets/") for name in file_entries):
                self._reject(
                    rejections,
                    code=ImportRejectionCode.INVALID_ZIP,
                    object_type="package",
                    object_id="assets/",
                    stage=ImportStage.ZIP_STRUCTURE,
                    message="标准 ZIP 必须包含 assets/ 目录",
                    next_action="按规格 5.4 补齐图片目录后重新上传",
                )
                return None
            unexpected = [
                name
                for name in file_entries
                if name not in _EXPECTED_TOP_LEVEL
                and not name.startswith(_REQUIRED_PREFIXES)
            ]
            if unexpected:
                unexpected.sort()
                self._reject(
                    rejections,
                    code=ImportRejectionCode.INVALID_ZIP,
                    object_type="zip_entry",
                    object_id=unexpected[0],
                    stage=ImportStage.ZIP_STRUCTURE,
                    message="ZIP 根目录只允许 manifest.json、cases/、assets/ 与 checksums.json",
                    next_action="移除多余顶层文件后重新上传",
                )
                return None
            nested = [name for name in file_entries if name.lower().endswith(".zip")]
            if nested:
                nested.sort()
                self._reject(
                    rejections,
                    code=ImportRejectionCode.INVALID_ZIP,
                    object_type="zip_entry",
                    object_id=nested[0],
                    stage=ImportStage.ZIP_STRUCTURE,
                    message="不允许嵌套 ZIP，一次只接收一个 ZIP",
                    next_action="移除包内 ZIP 压缩文件后重新上传",
                )
                return None
            try:
                for name in file_entries:
                    archive.extract(name, sandbox)
            except (zipfile.BadZipFile, NotImplementedError, RuntimeError, KeyError, OSError):
                self._reject(
                    rejections,
                    code=ImportRejectionCode.INVALID_ZIP,
                    object_type="package",
                    object_id="",
                    stage=ImportStage.ZIP_STRUCTURE,
                    message="ZIP 内容损坏或使用了不支持的压缩方式",
                    next_action="使用标准 ZIP 压缩工具重新组包后上传",
                )
                return None

        # 双保险：落盘文件必须仍在沙箱内且为普通文件（防路径规范化绕过）。
        sandbox_resolved = sandbox.resolve()
        for name in file_entries:
            dest = (sandbox / name).resolve()
            try:
                dest.relative_to(sandbox_resolved)
            except ValueError:
                self._reject(
                    rejections,
                    code=ImportRejectionCode.INVALID_ZIP,
                    object_type="zip_entry",
                    object_id=name,
                    stage=ImportStage.ZIP_STRUCTURE,
                    message="文件解压后越出临时沙箱",
                    next_action="检查案例包路径后重新上传",
                )
                return None
            if dest.is_symlink():
                self._reject(
                    rejections,
                    code=ImportRejectionCode.INVALID_ZIP,
                    object_type="zip_entry",
                    object_id=name,
                    stage=ImportStage.ZIP_STRUCTURE,
                    message="不允许符号链接条目",
                    next_action="以普通文件重新组包后上传",
                )
                return None
        return file_entries

    def _validate_entry(
        self,
        info: zipfile.ZipInfo,
        seen: set[str],
        rejections: list[RejectionInfo],
    ) -> str | None:
        """校验单个 ZIP 条目；返回 'file'/'dir'，拒绝时返回 None 并记录。"""
        name = info.filename
        if name in seen:
            self._reject(
                rejections,
                code=ImportRejectionCode.INVALID_ZIP,
                object_type="zip_entry",
                object_id=name,
                stage=ImportStage.ZIP_STRUCTURE,
                message="ZIP 内不允许重复条目名",
                next_action="移除重复条目后重新组包",
            )
            return None
        seen.add(name)
        if not name or name.startswith(("/", "\\")) or "\\" in name or _DRIVE_LETTER.match(name):
            self._reject(
                rejections,
                code=ImportRejectionCode.INVALID_ZIP,
                object_type="zip_entry",
                object_id=name or "(空名)",
                stage=ImportStage.ZIP_STRUCTURE,
                message="条目路径必须为包内相对路径且仅使用 '/' 分隔符",
                next_action="修正包内相对路径后重新组包",
            )
            return None
        if _ENCODED_PATH_CHARS.search(name):
            self._reject(
                rejections,
                code=ImportRejectionCode.INVALID_ZIP,
                object_type="zip_entry",
                object_id=name,
                stage=ImportStage.ZIP_STRUCTURE,
                message="条目路径不得包含 URL 编码的点或分隔符",
                next_action="修正包内路径后重新组包",
            )
            return None
        is_dir = info.is_dir()
        segments = name.rstrip("/").split("/") if is_dir else name.split("/")
        if any(segment in ("..", ".", "") for segment in segments):
            self._reject(
                rejections,
                code=ImportRejectionCode.INVALID_ZIP,
                object_type="zip_entry",
                object_id=name,
                stage=ImportStage.ZIP_STRUCTURE,
                message="条目路径不得包含 '..'、'.' 或空段",
                next_action="修正包内相对路径后重新组包",
            )
            return None
        mode = (info.external_attr >> 16) & 0o170000
        if mode and not is_dir and mode != stat.S_IFREG:
            self._reject(
                rejections,
                code=ImportRejectionCode.INVALID_ZIP,
                object_type="zip_entry",
                object_id=name,
                stage=ImportStage.ZIP_STRUCTURE,
                message="不允许符号链接或特殊文件条目",
                next_action="以普通文件重新组包后上传",
            )
            return None
        return "dir" if is_dir else "file"

    # ---------- 第二步：manifest、checksums 合同与逐案例校验 ----------

    def _check_manifest_and_cases(
        self,
        sandbox: Path,
        file_entries: dict[str, zipfile.ZipInfo],
        rejections: list[RejectionInfo],
    ) -> _ParsedPackage | None:
        manifest_bytes = (sandbox / "manifest.json").read_bytes()
        try:
            manifest = BatchManifest.model_validate_json(manifest_bytes)
        except (ValidationError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            detail = (
                _first_validation_issue(exc)
                if isinstance(exc, ValidationError)
                else "JSON 无法解析"
            )
            self._reject(
                rejections,
                code=ImportRejectionCode.INVALID_ZIP,
                object_type="manifest",
                object_id="manifest.json",
                stage=ImportStage.MANIFEST,
                message=f"manifest.json 不满足批清单合同：{detail}",
                next_action="按规格 5.4 修正 manifest.json 后重新组包",
            )
            return None

        actual_cases = sorted(
            name for name in file_entries if name.startswith("cases/")
        )
        expected_cases = sorted(manifest.case_files)
        if actual_cases != expected_cases:
            missing = sorted(set(expected_cases) - set(actual_cases))
            extra = sorted(set(actual_cases) - set(expected_cases))
            self._reject(
                rejections,
                code=ImportRejectionCode.INVALID_ZIP,
                object_type="manifest",
                object_id="manifest.json",
                stage=ImportStage.MANIFEST,
                message=(
                    f"manifest.case_files 与实际 cases 文件不一致"
                    f"（缺失 {len(missing)} 个、多余 {len(extra)} 个）"
                ),
                next_action="核对 manifest.case_files 与实际案例文件后重新组包",
            )
            return None

        checksum_bytes = (sandbox / "checksums.json").read_bytes()
        try:
            checksums = Checksums.model_validate_json(checksum_bytes)
        except (ValidationError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            detail = (
                _first_validation_issue(exc)
                if isinstance(exc, ValidationError)
                else "JSON 无法解析"
            )
            self._reject(
                rejections,
                code=ImportRejectionCode.INVALID_ZIP,
                object_type="checksums",
                object_id="checksums.json",
                stage=ImportStage.CHECKSUMS,
                message=f"checksums.json 不满足校验和合同：{detail}",
                next_action="按规格 5.4 重新生成 checksums.json",
            )
            return None

        cases: list[tuple[str, CaseInput]] = []
        for case_file in expected_cases:
            case_bytes = (sandbox / case_file).read_bytes()
            try:
                payload = json.loads(case_bytes)
            except (json.JSONDecodeError, UnicodeDecodeError):
                self._reject(
                    rejections,
                    code=ImportRejectionCode.INPUT_CONTRACT_INVALID,
                    object_type="case",
                    object_id=case_file,
                    stage=ImportStage.CASE_CONTRACT,
                    message="案例文件不是有效的 UTF-8 JSON",
                    next_action="按规格 5.5 修正案例 JSON 后重新组包",
                )
                continue
            findings = _leak_findings(payload) + _text_privacy_findings(payload)
            if findings:
                for finding in findings:
                    self._reject(
                        rejections,
                        code=ImportRejectionCode.ANSWER_LEAKAGE_DETECTED,
                        object_type="case",
                        object_id=case_file,
                        stage=ImportStage.ANSWER_LEAKAGE,
                        message=finding.message,
                        next_action="移除答案或未脱敏内容后重新组包",
                    )
                continue
            try:
                cases.append((case_file, CaseInput.model_validate(payload)))
            except ValidationError as exc:
                self._reject(
                    rejections,
                    code=ImportRejectionCode.INPUT_CONTRACT_INVALID,
                    object_type="case",
                    object_id=case_file,
                    stage=ImportStage.CASE_CONTRACT,
                    message=f"CaseInput 不满足运行合同：{_first_validation_issue(exc)}",
                    next_action="按规格 5.5—5.6 修正案例后重新组包",
                )
        if rejections:
            return None
        return _ParsedPackage(manifest=manifest, checksums=checksums, cases=cases)

    # ---------- 第三步：文件清单、校验值、关系与媒体 ----------

    def _check_relationships_and_media(
        self,
        sandbox: Path,
        file_entries: dict[str, zipfile.ZipInfo],
        parsed: _ParsedPackage,
        rejections: list[RejectionInfo],
    ) -> None:
        manifest = parsed.manifest
        cases = parsed.cases
        asset_media: dict[str, ImageMediaType] = {}
        asset_evidence: dict[str, list[ImageEvidenceItem]] = {}
        for _file, case in cases:
            for item in case.evidence.image_items:
                asset_media[item.asset_relative_path] = item.media_type
                asset_evidence.setdefault(item.asset_relative_path, []).append(item)

        asset_refs = set(asset_media)
        # expected_files 含 manifest.json（校验和必须覆盖 manifest），但 ZIP 的实际
        # 非顶层文件只包含 cases/ 与 assets/：清单对比要在同一基准上进行。
        expected_files = {"manifest.json"} | set(manifest.case_files) | asset_refs
        expected_case_and_asset = set(manifest.case_files) | asset_refs
        actual_case_and_asset = set(file_entries) - _EXPECTED_TOP_LEVEL
        if actual_case_and_asset != expected_case_and_asset:
            missing = sorted(expected_case_and_asset - actual_case_and_asset)
            extra = sorted(actual_case_and_asset - expected_case_and_asset)
            self._reject(
                rejections,
                code=ImportRejectionCode.INVALID_ZIP,
                object_type="package",
                object_id="",
                stage=ImportStage.RELATIONSHIP,
                message=(
                    f"ZIP 文件清单与 manifest/证据引用不一致"
                    f"（缺失 {len(missing)} 项、多余 {len(extra)} 项）"
                ),
                next_action="确保 assets 只包含案例实际引用的图片后重新组包",
            )
            return

        expected_keys = set(expected_files)
        if set(parsed.checksums.root) != expected_keys:
            missing = sorted(expected_keys - set(parsed.checksums.root))
            extra = sorted(set(parsed.checksums.root) - expected_keys)
            self._reject(
                rejections,
                code=ImportRejectionCode.INVALID_ZIP,
                object_type="checksums",
                object_id="checksums.json",
                stage=ImportStage.CHECKSUMS,
                message=(
                    f"checksums.json 键集合必须恰好覆盖 manifest、全部案例与全部图片"
                    f"（缺失 {len(missing)} 项、多余 {len(extra)} 项）"
                ),
                next_action="重新生成与包内容一致的 checksums.json",
            )
            return

        for rel in sorted(expected_files):
            actual_sha = hashlib.sha256((sandbox / rel).read_bytes()).hexdigest()
            if actual_sha != parsed.checksums.root[rel]:
                self._reject(
                    rejections,
                    code=ImportRejectionCode.INVALID_ZIP,
                    object_type="file",
                    object_id=rel,
                    stage=ImportStage.CHECKSUMS,
                    message="文件内容与 checksums.json 校验和不一致",
                    next_action="重新生成 checksums.json 后重新组包",
                )
        if rejections:
            return

        total_evidence = sum(
            len(case.evidence.text_items)
            + len(case.evidence.image_items)
            + len(case.evidence.behavior_items)
            for _file, case in cases
        )
        if total_evidence != manifest.evidence_count:
            self._reject(
                rejections,
                code=ImportRejectionCode.INVALID_ZIP,
                object_type="manifest",
                object_id="manifest.json",
                stage=ImportStage.RELATIONSHIP,
                message=(
                    f"manifest.evidence_count（{manifest.evidence_count}）"
                    f"与实际证据总数（{total_evidence}）不一致"
                ),
                next_action="按实际证据数修正 manifest.json 后重新组包",
            )

        for case_file, case in cases:
            if case.batch_id != manifest.batch_id:
                self._reject(
                    rejections,
                    code=ImportRejectionCode.INPUT_CONTRACT_INVALID,
                    object_type="case",
                    object_id=case_file,
                    stage=ImportStage.RELATIONSHIP,
                    message="案例 batch_id 与 manifest.batch_id 不一致",
                    next_action="统一 batch_id 后重新组包",
                )
            if case.data_version != manifest.data_version:
                self._reject(
                    rejections,
                    code=ImportRejectionCode.INPUT_CONTRACT_INVALID,
                    object_type="case",
                    object_id=case_file,
                    stage=ImportStage.RELATIONSHIP,
                    message="案例 data_version 与 manifest.data_version 不一致",
                    next_action="统一 data_version 后重新组包",
                )

        seen_case_ids: dict[str, str] = {}
        for case_file, case in cases:
            if case.case_id in seen_case_ids:
                self._reject(
                    rejections,
                    code=ImportRejectionCode.INPUT_CONTRACT_INVALID,
                    object_type="case",
                    object_id=case_file,
                    stage=ImportStage.RELATIONSHIP,
                    message=f"case_id（{case.case_id}）在批次内重复",
                    next_action="确保 case_id 在批次内唯一后重新组包",
                )
            seen_case_ids[case.case_id] = case_file

        for asset_path in sorted(asset_media):
            media_type = asset_media[asset_path]
            suffix = PurePosixPath(asset_path).suffix.lower()
            expected_type = _IMAGE_EXTENSION_TO_MEDIA_TYPE.get(suffix)
            if expected_type is None:
                self._reject(
                    rejections,
                    code=ImportRejectionCode.UNSUPPORTED_MEDIA_TYPE,
                    object_type="asset",
                    object_id=asset_path,
                    stage=ImportStage.MEDIA,
                    message="图片只接受 .jpg/.jpeg/.png/.gif 扩展名",
                    next_action="使用支持的图片格式后重新组包",
                )
                continue
            if expected_type != media_type:
                self._reject(
                    rejections,
                    code=ImportRejectionCode.UNSUPPORTED_MEDIA_TYPE,
                    object_type="asset",
                    object_id=asset_path,
                    stage=ImportStage.MEDIA,
                    message="图片扩展名与声明的 media_type 不一致",
                    next_action="统一扩展名与 media_type 后重新组包",
                )
                continue
            data = (sandbox / asset_path).read_bytes()
            if not any(data.startswith(magic) for magic in _MEDIA_MAGIC[media_type]):
                self._reject(
                    rejections,
                    code=ImportRejectionCode.UNSUPPORTED_MEDIA_TYPE,
                    object_type="asset",
                    object_id=asset_path,
                    stage=ImportStage.MEDIA,
                    message="图片内容魔数与声明的 media_type 不一致",
                    next_action="替换为真实图片文件后重新组包",
                )
                continue
            actual_sha = hashlib.sha256(data).hexdigest()
            for item in asset_evidence[asset_path]:
                if item.content_hash != actual_sha:
                    self._reject(
                        rejections,
                        code=ImportRejectionCode.INVALID_ZIP,
                        object_type="asset",
                        object_id=asset_path,
                        stage=ImportStage.RELATIONSHIP,
                        message="图片证据 content_hash 与实际图片文件不一致",
                        next_action="按图片原文件重算 content_hash 后重新组包",
                    )


