"""M1-03 ZIP 暂存与校验测试构造助手（M1-08 ReviewStore 测试复用；独立命名模块）。

以 M1-01（tests/fixtures/runtime/contracts/）的合法样例为基底生成完整标准 ZIP：
- manifest.json / checksums.json / cases/ / assets/ 齐备；
- checksums.json 始终按实际写入字节重新计算，保证"绝对值匹配"；
- 负向用例通过改写条目、增减文件或注入 ZipInfo 属性构造（M1-03 恶意包夹具）。

辅助函数放在独立模块而非 conftest.py：pytest 会把 tests/m1/db 与 tests/m1/importing
两个无 __init__.py 的目录同时插入 sys.path，顶层 conftest 模块名会互相遮蔽。
"""

from __future__ import annotations

import copy
import hashlib
import io
import json
import stat
import zipfile
from collections.abc import Callable
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "runtime" / "contracts"

# 最小图片样本：魔数完整、可被内容哈希与魔数校验识别（本卡只校验魔数与哈希）。
JPEG_BYTES = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"
)
PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
    b"\x1f\x15\xc4\x89\x00\x00\x00\x0cIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
    b"\x0d\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)
GIF_BYTES = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff"
    b"!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01"
    b"\x00\x00\x02\x02D\x01\x00;"
)

MVP_CASE_IDS = ("mvp_case_001", "mvp_case_002")


def load_fixture(name: str) -> dict:
    with (FIXTURES_DIR / name).open("r", encoding="utf-8") as fh:
        return json.load(fh)


def json_bytes(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_case(
    case_id: str,
    *,
    image_suffix: str = ".jpg",
    media_type: str = "image/jpeg",
    image_bytes: bytes = JPEG_BYTES,
) -> dict:
    """基于合法样例生成一个 CaseInput 字典；图片证据哈希按真实图片字节计算。"""
    payload = copy.deepcopy(load_fixture("valid_case_input.json"))
    payload["case_id"] = case_id
    payload["evidence"]["image_items"][0] = {
        **payload["evidence"]["image_items"][0],
        "evidence_id": f"ev_image_{case_id}",
        "asset_relative_path": f"assets/{case_id}/scratch_01{image_suffix}",
        "media_type": media_type,
        "content_hash": sha256_bytes(image_bytes),
    }
    for idx, item in enumerate(payload["evidence"]["text_items"], start=1):
        item["evidence_id"] = f"ev_text_{case_id}_{idx}"
    for idx, item in enumerate(payload["evidence"]["behavior_items"], start=1):
        item["evidence_id"] = f"ev_behavior_{case_id}_{idx}"
    return payload


def make_manifest(
    case_ids: tuple[str, ...] = MVP_CASE_IDS,
    *,
    evidence_count: int | None = None,
) -> dict:
    """生成合法 manifest：case_files 升序、case_count 与列表一致。"""
    payload = copy.deepcopy(load_fixture("valid_manifest.json"))
    payload["case_files"] = [f"cases/{case_id}.json" for case_id in sorted(case_ids)]
    payload["case_count"] = len(case_ids)
    payload["evidence_count"] = (
        evidence_count if evidence_count is not None else 7 * len(case_ids)
    )
    return payload


def make_entries(
    *,
    case_ids: tuple[str, ...] = MVP_CASE_IDS,
    case_builder: Callable[[str], dict] = make_case,
    manifest_overrides: dict[str, object] | None = None,
    image_bytes: bytes = JPEG_BYTES,
    image_suffix: str = ".jpg",
    extra: dict[str, bytes] | None = None,
    drop: tuple[str, ...] = (),
    keep_checksums: bool = False,
) -> dict[str, bytes]:
    """生成完整标准 ZIP 条目（不缺 checksums）；checksums 默认按实际字节重算。"""
    manifest = make_manifest(case_ids)
    if manifest_overrides:
        manifest.update(manifest_overrides)
    entries: dict[str, bytes] = {
        "manifest.json": json_bytes(manifest),
        "checksums.json": b"",
    }
    for case_id in case_ids:
        entries[f"cases/{case_id}.json"] = json_bytes(case_builder(case_id))
        entries[f"assets/{case_id}/scratch_01{image_suffix}"] = image_bytes
    for name in drop:
        entries.pop(name, None)
    if extra:
        entries.update(extra)
    if keep_checksums:
        return entries
    checksums = {
        name: sha256_bytes(data)
        for name, data in sorted(entries.items())
        if name != "checksums.json"
    }
    entries["checksums.json"] = json_bytes(checksums)
    return entries


def make_zip(
    entries: dict[str, bytes],
    *,
    symlinks: dict[str, str] | None = None,
) -> bytes:
    """按相对路径升序写入 ZIP，条目时间戳/权限固定；可选注入符号链接条目。"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name in sorted(entries):
            info = zipfile.ZipInfo(name, date_time=(2024, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o100644) << 16
            zf.writestr(info, entries[name])
        for name, target in (symlinks or {}).items():
            info = zipfile.ZipInfo(name, date_time=(2024, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            zf.writestr(info, target)
    return buffer.getvalue()

