"""M1-03 结构安全测试：ZIP 结构、路径安全、符号链接、清理与错误报告约定。

对应技术实施规格 M1-03 自动验收：路径穿越、绝对路径、符号链接；人工验收：
每类拒绝都有稳定编号与可操作说明，不含本机路径与客户正文（规格 12.4）。
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from zip_fixtures import (
    REPO_ROOT,
    make_entries,
    make_zip,
)

from app.contracts.data import PackageType
from app.modules.data.importing.errors import ImportRejectionCode, ImportStage

# 路径穿越 / 绝对路径 / 编码分隔符恶意条目（zipfile 不解析 %xx，按字面文件名写入）。
_EVIL_NAMES = (
    "../evil.txt",
    "cases/../../evil.json",
    "..\\..\\evil.txt",
    "cases/..\\evil.json",
    "C:/windows/system32/drivers/etc/host",
    "C:\\windows\\system32\\evil.dll",
    "/etc/passwd",
    "\\\\.\\CON",
    "assets/..%2f..%2fsecret.txt",
    "assets/%2e%2e/secret.txt",
    "cases/%2e%2e%2fevil.json",
    "cases/./x.json",
    "cases//x.json",
)


def _codes(result) -> set[str]:
    return {r.code.value for r in result.rejections}


def test_valid_demo_zip_passes_and_reports_summary(stage) -> None:
    raw = make_zip(make_entries())
    result = stage.stage(raw, source_filename="demo_batch_v1.zip")
    assert result.ok
    assert result.rejections == ()
    assert result.package_type == PackageType.DEMO
    assert result.case_count == 2
    assert result.evidence_count == 14
    assert result.is_mock is True
    assert result.source_filename == "demo_batch_v1.zip"
    assert len(result.package_sha256) == 64
    import hashlib

    assert result.package_sha256 == hashlib.sha256(raw).hexdigest()


def test_valid_zip_accepts_binary_stream(stage) -> None:
    result = stage.stage(io.BytesIO(make_zip(make_entries())))
    assert result.ok
    assert result.case_count == 2


def test_success_cleans_up_temp_sandbox(stage, tmp_root: Path) -> None:
    result = stage.stage(make_zip(make_entries()))
    assert result.ok
    assert list(tmp_root.iterdir()) == []


def test_rejection_cleans_up_temp_sandbox(stage, tmp_root: Path) -> None:
    result = stage.stage(b"not a zip")
    assert not result.ok
    assert list(tmp_root.iterdir()) == []


def test_default_tmp_root_is_runtime_data_imports_tmp() -> None:
    from app.modules.data.importing.zip_stage import DEFAULT_TMP_ROOT

    assert DEFAULT_TMP_ROOT.parts[-3:] == ("runtime_data", "imports", "tmp")


def test_non_zip_bytes_rejected(stage) -> None:
    result = stage.stage(b"hello, this is not a zip archive at all")
    assert not result.ok
    assert _codes(result) == {ImportRejectionCode.INVALID_ZIP.value}


@pytest.mark.parametrize("evil_name", _EVIL_NAMES)
def test_unsafe_paths_rejected(stage, evil_name: str) -> None:
    entries = make_entries(extra={evil_name: b"evil"})
    result = stage.stage(make_zip(entries))
    assert not result.ok
    assert ImportRejectionCode.INVALID_ZIP.value in _codes(result)
    assert any(
        r.stage == ImportStage.ZIP_STRUCTURE for r in result.rejections
    )


def test_symlink_entry_rejected(stage) -> None:
    raw = make_zip(
        make_entries(),
        symlinks={"assets/evil-link": "../../manifest.json"},
    )
    result = stage.stage(raw)
    assert not result.ok
    assert ImportRejectionCode.INVALID_ZIP.value in _codes(result)
    messages = [r.message for r in result.rejections]
    assert any("符号链接" in message for message in messages)


def test_duplicate_entry_names_rejected(stage) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for _ in range(2):
            zf.writestr("cases/demo_case_001.json", b"{}")
    result = stage.stage(buffer.getvalue())
    assert not result.ok
    assert any("重复条目名" in r.message for r in result.rejections)


@pytest.mark.parametrize(
    "dropped",
    (
        ("manifest.json",),
        ("checksums.json",),
        ("cases/demo_case_001.json", "cases/demo_case_002.json"),
        ("assets/demo_case_001/scratch_01.jpg", "assets/demo_case_002/scratch_01.jpg"),
    ),
)
def test_missing_required_members_rejected(stage, dropped: tuple[str, ...]) -> None:
    # keep_checksums=True：不按最终字节重算，否则被删的 checksums.json 会被重新生成。
    result = stage.stage(make_zip(make_entries(drop=dropped, keep_checksums=True)))
    assert not result.ok
    assert ImportRejectionCode.INVALID_ZIP.value in _codes(result)


def test_unexpected_top_level_file_rejected(stage) -> None:
    result = stage.stage(make_zip(make_entries(extra={"notes.txt": b"x"})))
    assert not result.ok
    assert any(
        r.stage == ImportStage.ZIP_STRUCTURE for r in result.rejections
    )


def test_nested_zip_rejected(stage) -> None:
    nested = make_zip(make_entries())
    result = stage.stage(make_zip(make_entries(extra={"assets/evil.zip": nested})))
    assert not result.ok
    assert any("嵌套 ZIP" in r.message for r in result.rejections)


def test_rejection_has_stable_actionable_fields(stage) -> None:
    result = stage.stage(b"not a zip")
    assert len(result.rejections) == 1
    rejection = result.rejections[0]
    assert rejection.code == ImportRejectionCode.INVALID_ZIP
    assert rejection.message
    assert rejection.object_type
    assert rejection.object_id
    assert rejection.stage in ImportStage
    assert rejection.next_action
    assert len(rejection.trace_id) == 32


def test_rejection_messages_do_not_contain_local_paths(
    stage, tmp_root: Path
) -> None:
    results = [
        stage.stage(make_zip(make_entries(extra={"../evil.txt": b"evil"}))),
        stage.stage(b"not a zip"),
        stage.stage(make_zip(make_entries(drop=("manifest.json",)))),
    ]
    messages = [r.message for result in results for r in result.rejections]
    forbidden = (
        str(REPO_ROOT),
        str(tmp_root),
        "D:\\",
        "D:/",
        "C:\\",
        "C:/",
        ".venv",
        "runtime_data",
    )
    for message in messages:
        for token in forbidden:
            assert token not in message
