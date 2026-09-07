"""M1-04：BatchImportGateway 原子导入（技术实施规格 3.1/5.4/8/11.1；ADR-0033/0079）。

把通过 M1-03 完整校验的单个 ZIP 原子发布为 PENDING_ANALYSIS 正式批次（规格 5.4
导入规则）：

- 同 package_sha256 再次导入返回已有批次，不重复写文件或落库（包哈希幂等）；
- batch_id 全局唯一：已有 batch_id 对应不同内容返回 BATCH_ID_CONFLICT（409）；
- 先写正式批次文件（沿用已通过校验的包条目），再在单个短事务内写
  data_versions/batches/cases/evidence 四表；任意文件或事务失败即回滚清理，
  正式目录与九表不留半成品（M1-04 自动验收）；
- 导入成功只生成 PENDING_ANALYSIS，不自动调用模型（M1-04 禁止事项）。

接口只接收 ZIP 字节流/二进制流与元信息，不接受服务器路径，不返回临时绝对路径
（规格 3.1/8）。可预期拒绝以 ImportResult.rejections 返回；意外异常记录技术日志
后映射为 INTERNAL_ERROR 拒绝，界面不暴露异常类名与本机路径（规格 12.4）。
"""

from __future__ import annotations

import hashlib
import io
import logging
import re
import shutil
import stat
import zipfile
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from typing import BinaryIO
from uuid import uuid4

from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from app.contracts.data import BatchManifest, CaseInput, PackageType
from app.contracts.states import BatchStatus

from ..db.models import Batch
from ..repositories.batch_import_repository import BatchImportRepository
from .errors import ImportRejectionCode, ImportStage, RejectionInfo
from .zip_stage import DEFAULT_MAX_ZIP_BYTES, DEFAULT_TMP_ROOT, ZipImportStage

_logger = logging.getLogger(__name__)

_DRIVE_LETTER = re.compile(r"^[A-Za-z]:")
_ENCODED_PATH_CHARS = re.compile(r"%(?:2e|2f|5c)", re.IGNORECASE)
_ILLEGAL_DIR_SEGMENTS = frozenset({"", ".", ".."})


@dataclass(frozen=True, slots=True)
class ImportResult:
    """导入摘要或逐项拒绝（规格 3.1/8/12.2；M1-04 输出）。

    成功（ok=True）：imported 与 returned_existing 之一为 True，并给出原文件名、
    batch_id、状态、案例数、证据数与 Mock 标记；拒绝（ok=False）时 rejections
    非空，业务字段保持 None。
    """

    ok: bool
    source_filename: str
    batch_id: str | None = None
    status: str | None = None
    package_type: PackageType | None = None
    package_sha256: str | None = None
    case_count: int | None = None
    evidence_count: int | None = None
    is_mock: bool | None = None
    imported: bool = False
    returned_existing: bool = False
    rejections: tuple[RejectionInfo, ...] = ()
    trace_id: str = ""


def _is_safe_dir_component(value: str) -> bool:
    """正式批次目录名安全：非空、可打印、无分隔符/驱动符/'.'/ '..' 越界段。"""
    if not value or not value.isprintable() or len(value) > 128:
        return False
    if value in _ILLEGAL_DIR_SEGMENTS or "/" in value or "\\" in value:
        return False
    return _DRIVE_LETTER.match(value) is None


def _walk_relative_files(root: Path) -> list[str]:
    """root 下全部普通文件的相对正斜杠路径（升序，供正式目录回写）。"""
    return sorted(
        path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()
    )


class BatchImportGateway:
    """SQLite 版 BatchImportGateway：原子发布通过校验的 ZIP 为正式批次。

    formal_root 为运行数据根（默认项目根下的 runtime_data/，ADR-0033），其下
    batches/<batch_id>/<data_version>/ 为正式批次目录；数据库只保存相对该根的包路径
    与文件哈希，不存绝对路径（规格 11.2/11.3）。
    """

    def __init__(
        self,
        *,
        engine: Engine,
        formal_root: Path,
        tmp_root: Path | None = None,
        max_zip_bytes: int = DEFAULT_MAX_ZIP_BYTES,
    ) -> None:
        self.formal_root = Path(formal_root)
        self.tmp_root = Path(tmp_root) if tmp_root is not None else DEFAULT_TMP_ROOT
        self.max_zip_bytes = max_zip_bytes
        self.repository = BatchImportRepository(engine)
        self.stage = ZipImportStage(tmp_root=self.tmp_root, max_zip_bytes=max_zip_bytes)

    def import_zip(
        self,
        source: bytes | BinaryIO,
        *,
        source_filename: str = "upload.zip",
        content_length: int | None = None,
        trace_id: str | None = None,
    ) -> ImportResult:
        """导入单个 ZIP：返回导入摘要或逐项拒绝，不抛业务异常、不调用模型。"""
        trace = trace_id if trace_id is not None else uuid4().hex
        try:
            raw = source if isinstance(source, bytes) else source.read()
            if not isinstance(raw, bytes):
                raise TypeError("ZIP 输入必须是 bytes 或二进制流")
            if content_length is not None and content_length > self.max_zip_bytes:
                return self._reject(
                    trace=trace,
                    source_filename=source_filename,
                    code=ImportRejectionCode.UPLOAD_TOO_LARGE,
                    object_type="upload",
                    object_id=source_filename,
                    message=f"ZIP 超过上传大小上限（{self.max_zip_bytes} 字节）",
                    next_action="裁剪或压缩案例后重新上传",
                )
            package_sha256 = hashlib.sha256(raw).hexdigest()
            existing = self.repository.find_batch_by_package_sha256(package_sha256)
            if existing is not None:
                return self._existing_summary(existing, source_filename, trace)
            staged = self.stage.stage(raw, source_filename=source_filename)
            if not staged.ok:
                return ImportResult(
                    ok=False,
                    source_filename=staged.source_filename,
                    rejections=tuple(
                        replace(rejection, trace_id=trace) for rejection in staged.rejections
                    ),
                    trace_id=trace,
                )
            assert staged.package_sha256 == package_sha256
            return self._publish(raw, package_sha256, source_filename, trace)
        except Exception:
            _logger.exception("BatchImportGateway 未预期异常，trace_id=%s", trace)
            return self._reject(
                trace=trace,
                source_filename=source_filename,
                code=ImportRejectionCode.INTERNAL_ERROR,
                object_type="package",
                object_id="",
                message="导入过程发生内部错误，详情见技术日志",
                next_action="查看技术日志后重试",
            )

    # ---------- 正式发布：先写文件、单事务落库、失败全量清理 ----------

    def _publish(
        self,
        raw: bytes,
        package_sha256: str,
        source_filename: str,
        trace: str,
    ) -> ImportResult:
        temp_dir = self.tmp_root / uuid4().hex
        temp_dir.mkdir(parents=True, exist_ok=True)
        try:
            try:
                self._extract_safely(raw, temp_dir)
                manifest = self._read_manifest(temp_dir)
                cases = self._read_cases(temp_dir, manifest)
            except Exception:
                _logger.exception("已通过校验的包内容解析失败，trace_id=%s", trace)
                return self._reject(
                    trace=trace,
                    source_filename=source_filename,
                    code=ImportRejectionCode.INTERNAL_ERROR,
                    object_type="package",
                    object_id="",
                    message="已通过校验的包内容解析失败，详情见技术日志",
                    next_action="查看技术日志后重试",
                )

            existing = self.repository.find_batch_by_package_sha256(package_sha256)
            if existing is not None:
                return self._existing_summary(existing, source_filename, trace)
            conflict = self.repository.find_batch_by_batch_id(manifest.batch_id)
            if conflict is not None and conflict.package_sha256 != package_sha256:
                return self._reject(
                    trace=trace,
                    source_filename=source_filename,
                    code=ImportRejectionCode.BATCH_ID_CONFLICT,
                    object_type="batch",
                    object_id=manifest.batch_id,
                    message=f"batch_id（{manifest.batch_id}）已存在且内容与本次上传不一致",
                    next_action="使用新的 batch_id 重新组包，或上传原包内容",
                )
            if conflict is not None:
                return self._existing_summary(conflict, source_filename, trace)

            for field, value in (
                ("batch_id", manifest.batch_id),
                ("data_version", manifest.data_version),
            ):
                if not _is_safe_dir_component(value):
                    return self._reject(
                        trace=trace,
                        source_filename=source_filename,
                        code=ImportRejectionCode.INPUT_CONTRACT_INVALID,
                        object_type="manifest",
                        object_id=f"manifest.json/{field}",
                        message=f"manifest.{field} 不能作为正式批次目录名（路径越界风险）",
                        next_action="使用不含分隔符的 batch_id/data_version 重新组包",
                    )

            batch_relative_path = f"batches/{manifest.batch_id}/{manifest.data_version}"
            formal_dir = (
                self.formal_root
                / "batches"
                / manifest.batch_id
                / manifest.data_version
            )
            try:
                formal_dir.mkdir(parents=True, exist_ok=True)
                self._write_formal_package(temp_dir, formal_dir, source_filename)
                self.repository.persist_import(
                    manifest=manifest,
                    cases=cases,
                    package_sha256=package_sha256,
                    package_relative_path=batch_relative_path,
                )
            except IntegrityError:
                self._cleanup_formal_dir(formal_dir)
                existing = self.repository.find_batch_by_package_sha256(package_sha256)
                if existing is not None:
                    return self._existing_summary(existing, source_filename, trace)
                conflict = self.repository.find_batch_by_batch_id(manifest.batch_id)
                if conflict is not None:
                    return self._reject(
                        trace=trace,
                        source_filename=source_filename,
                        code=ImportRejectionCode.BATCH_ID_CONFLICT,
                        object_type="batch",
                        object_id=conflict.batch_id,
                        message=f"batch_id（{conflict.batch_id}）已存在且内容与本次上传不一致",
                        next_action="使用新的 batch_id 重新组包，或上传原包内容",
                    )
                raise
            except Exception:
                self._cleanup_formal_dir(formal_dir)
                _logger.exception("正式批次文件写入或落库失败，trace_id=%s", trace)
                return self._reject(
                    trace=trace,
                    source_filename=source_filename,
                    code=ImportRejectionCode.INTERNAL_ERROR,
                    object_type="package",
                    object_id=manifest.batch_id,
                    message="正式批次发布失败，已回滚清理，未留下半批次",
                    next_action="查看技术日志后重试",
                )
            return ImportResult(
                ok=True,
                source_filename=source_filename,
                batch_id=manifest.batch_id,
                status=BatchStatus.PENDING_ANALYSIS.value,
                package_type=manifest.package_type,
                package_sha256=package_sha256,
                case_count=manifest.case_count,
                evidence_count=manifest.evidence_count,
                is_mock=manifest.is_mock,
                imported=True,
                trace_id=trace,
            )
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def _existing_summary(
        self, batch: Batch, incoming_filename: str, trace: str
    ) -> ImportResult:
        """幂等命中：读回已保存包的文件名、Mock 标记与 evidence 表计数（规格 12.2）。"""
        rel_parts = PurePosixPath(batch.package_relative_path).parts
        # package_relative_path = batches/<batch_id>/<data_version>，相对 formal_root 保存，
        # 与 _publish 的 formal_root/batches/<batch_id>/<data_version> 保持一致。
        formal_dir = self.formal_root.joinpath(*rel_parts)
        try:
            manifest = BatchManifest.model_validate_json(
                (formal_dir / "manifest.json").read_bytes()
            )
            saved_filename = (formal_dir / "source_filename.txt").read_text(
                encoding="utf-8"
            ).strip()
        except Exception:
            _logger.exception("读取已有批次正式文件失败，batch_id=%s", batch.batch_id)
            return self._reject(
                trace=trace,
                source_filename=incoming_filename,
                code=ImportRejectionCode.INTERNAL_ERROR,
                object_type="batch",
                object_id=batch.batch_id,
                message="读取已有批次正式文件失败，详情见技术日志",
                next_action="检查正式批次目录后重试",
            )
        return ImportResult(
            ok=True,
            source_filename=saved_filename or incoming_filename,
            batch_id=batch.batch_id,
            status=batch.status.value,
            package_type=manifest.package_type,
            package_sha256=batch.package_sha256,
            case_count=batch.case_count,
            evidence_count=self.repository.evidence_count_for_batch(batch.id),
            is_mock=manifest.is_mock,
            returned_existing=True,
            trace_id=trace,
        )

    # ---------- 包条目安全解压与正式文件回写 ----------

    def _extract_safely(self, raw: bytes, dest: Path) -> list[str]:
        """把 ZIP 条目按与 M1-03 相同的路径安全规则解压到 dest（防御第二层）。"""
        try:
            archive = zipfile.ZipFile(io.BytesIO(raw))
        except zipfile.BadZipFile as exc:
            raise ValueError("ZIP 无法解析") from exc
        names: list[str] = []
        seen: set[str] = set()
        with archive:
            for info in archive.infolist():
                name = info.filename
                if (
                    not name
                    or name.startswith(("/", "\\"))
                    or "\\" in name
                    or _DRIVE_LETTER.match(name) is not None
                ):
                    raise ValueError(f"拒绝非法条目路径：{name!r}")
                if _ENCODED_PATH_CHARS.search(name) is not None:
                    raise ValueError(f"拒绝编码分隔符条目：{name!r}")
                segments = (
                    name.rstrip("/").split("/") if info.is_dir() else name.split("/")
                )
                if any(segment in _ILLEGAL_DIR_SEGMENTS for segment in segments):
                    raise ValueError(f"拒绝越界路径条目：{name!r}")
                mode = (info.external_attr >> 16) & 0o170000
                if mode and not info.is_dir() and mode != stat.S_IFREG:
                    raise ValueError(f"拒绝符号链接或特殊文件条目：{name!r}")
                if info.is_dir():
                    continue
                if name in seen:
                    raise ValueError(f"拒绝重复条目：{name!r}")
                seen.add(name)
                target = dest.joinpath(*PurePosixPath(name).parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(name))
                names.append(name)
        dest_resolved = dest.resolve()
        for name in names:
            target = (dest / name).resolve()
            if not target.is_relative_to(dest_resolved):
                raise ValueError(f"条目越出解压目录：{name!r}")
            if not target.is_file():
                raise ValueError(f"条目不是普通文件：{name!r}")
        return sorted(names)

    @staticmethod
    def _read_manifest(temp_dir: Path) -> BatchManifest:
        """读取已通过校验的 manifest（stage 已保证合同合格）。"""
        return BatchManifest.model_validate_json((temp_dir / "manifest.json").read_bytes())

    @staticmethod
    def _read_cases(
        temp_dir: Path, manifest: BatchManifest
    ) -> list[tuple[str, CaseInput]]:
        """按 manifest.case_files 顺序读回案例（stage 已保证文件存在且合同合格）。"""
        cases: list[tuple[str, CaseInput]] = []
        for case_file in manifest.case_files:
            case = CaseInput.model_validate_json((temp_dir / case_file).read_bytes())
            cases.append((case_file, case))
        return cases

    @staticmethod
    def _write_formal_package(
        temp_dir: Path, formal_dir: Path, source_filename: str
    ) -> None:
        """把已校验条目写入正式批次目录，并保存上传原文件名供 M3/M4 展示。"""
        for rel in _walk_relative_files(temp_dir):
            parts = PurePosixPath(rel).parts
            src = temp_dir.joinpath(*parts)
            dst = formal_dir.joinpath(*parts)
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(src.read_bytes())
        (formal_dir / "source_filename.txt").write_text(
            source_filename, encoding="utf-8"
        )

    @staticmethod
    def _cleanup_formal_dir(formal_dir: Path) -> None:
        """删除失败写入的正式批次目录；批次目录变空时一并移除（不留空壳）。"""
        shutil.rmtree(formal_dir, ignore_errors=True)
        try:
            formal_dir.parent.rmdir()
        except OSError:
            pass
    def _reject(
        self,
        *,
        trace: str,
        source_filename: str,
        code: ImportRejectionCode,
        object_type: str,
        object_id: str,
        message: str,
        next_action: str,
    ) -> ImportResult:
        """构造单条拒绝的导入结果；统一 stage=import 并透传 trace_id。"""
        return ImportResult(
            ok=False,
            source_filename=source_filename,
            rejections=(
                RejectionInfo(
                    code=code,
                    message=message,
                    object_type=object_type,
                    object_id=object_id,
                    stage=ImportStage.IMPORT,
                    next_action=next_action,
                    trace_id=trace,
                ),
            ),
            trace_id=trace,
        )
