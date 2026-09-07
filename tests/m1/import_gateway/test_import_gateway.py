"""M1-04 原子导入测试（技术实施规格 M1-04 自动验收 + 12.2/12.4 契约）。

覆盖：
- 新包创建一次：四表落库、PENDING_ANALYSIS、正式目录文件、摘要字段与证据投影；
- 同 package_sha256 幂等：返回原批次、不重复落库或写文件，source_filename 从
  已保存包文件名读取，evidence_count 由 evidence 表计数（规格 12.2）；
- 同 batch_id 异内容：BATCH_ID_CONFLICT 单条拒绝且无残留；
- 同 data_version 异 batch_id：data_versions 复用已有行；
- 任一文件写入或事务故障：正式目录与九表均无半成品（INTERNAL_ERROR）；
- 坏 ZIP / 超大小 / 字节流输入 / 目录名不安全：拒绝契约与 trace_id 透传。
"""

from __future__ import annotations

import hashlib
import io
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from zip_fixtures import make_case, make_entries, make_zip

from app.modules.data.db.models import Batch, Case, DataVersion, Evidence
from app.modules.data.importing.errors import ImportRejectionCode, ImportStage
from app.modules.data.importing.gateway import BatchImportGateway

DEMO_BATCH_ID = "demo_batch_v1"
DEMO_DATA_VERSION = "mock_dataset_v1"
TRACE = "trace-import"


def _wrapped_case(*, batch_id: str | None = None, data_version: str | None = None):
    """构造与 make_case 相同但覆盖 batch_id/data_version 的案例构造器。"""

    def builder(case_id: str) -> dict:
        payload = make_case(case_id)
        if batch_id is not None:
            payload["batch_id"] = batch_id
        if data_version is not None:
            payload["data_version"] = data_version
        return payload

    return builder


def _rows(engine: Engine, model: Any) -> list[Any]:
    with Session(engine) as session:
        return list(session.scalars(select(model)))


def _count(engine: Engine, model: Any) -> int:
    return len(_rows(engine, model))


def _counts(engine: Engine) -> tuple[int, int, int, int]:
    return (
        _count(engine, DataVersion),
        _count(engine, Batch),
        _count(engine, Case),
        _count(engine, Evidence),
    )



def _formal_dir(formal_root: Path, batch_id: str = DEMO_BATCH_ID) -> Path:
    return formal_root / "batches" / batch_id / DEMO_DATA_VERSION


def _single_rejection(result) -> Any:
    assert not result.ok
    assert len(result.rejections) == 1, result.rejections
    return result.rejections[0]


# ---------- 新包成功 ----------


def test_new_package_creates_pending_batch_and_formal_files(
    gateway: BatchImportGateway, engine: Engine, formal_root: Path
) -> None:
    raw = make_zip(make_entries())
    result = gateway.import_zip(raw, source_filename="demo_batch_v1.zip", trace_id=TRACE)

    assert result.ok
    assert result.imported and not result.returned_existing
    assert result.source_filename == "demo_batch_v1.zip"
    assert result.batch_id == DEMO_BATCH_ID
    assert result.status == "PENDING_ANALYSIS"
    assert result.package_type is not None and result.package_type.value == "DEMO"
    assert result.package_sha256 == hashlib.sha256(raw).hexdigest()
    assert result.case_count == 2
    assert result.evidence_count == 14
    assert result.is_mock is True
    assert result.rejections == ()
    assert result.trace_id == TRACE

    assert _counts(engine) == (1, 1, 2, 14)
    batch = next(row for row in _rows(engine, Batch) if row.batch_id == DEMO_BATCH_ID)
    assert batch.status.value == "PENDING_ANALYSIS"
    assert batch.analysis_succeeded_count == 0
    assert batch.error_count == 0
    assert batch.case_count == 2
    assert batch.package_sha256 == hashlib.sha256(raw).hexdigest()
    assert batch.package_relative_path == f"batches/{DEMO_BATCH_ID}/{DEMO_DATA_VERSION}"

    data_version_rows = _rows(engine, DataVersion)
    assert len(data_version_rows) == 1
    assert data_version_rows[0].data_version == DEMO_DATA_VERSION

    cases = _rows(engine, Case)
    assert {case.case_id for case in cases} == {"demo_case_001", "demo_case_002"}
    for case in cases:
        assert case.customer_display_id == "CUST-DEMO-000001"
        assert case.is_high_value is True
        assert case.status.value == "PENDING_ANALYSIS"

    evidence = _rows(engine, Evidence)
    assert Counter(row.modality for row in evidence) == {"text": 4, "image": 2, "behavior": 8}

    case_one = next(case for case in cases if case.case_id == "demo_case_001")
    ev = [row for row in evidence if row.case_id == case_one.id]
    text_rows = [row for row in ev if row.modality == "text"]
    assert {row.sequence_no for row in text_rows} == {1, 2}
    assert all(row.relative_path == "" and row.media_type == "text/plain" for row in text_rows)
    assert any("收到的商品有划痕" in row.payload_json["text"] for row in text_rows)
    image_rows = [row for row in ev if row.modality == "image"]
    assert len(image_rows) == 1
    assert image_rows[0].relative_path == "assets/demo_case_001/scratch_01.jpg"
    assert image_rows[0].media_type == "image/jpeg"
    assert image_rows[0].sequence_no == 0
    behavior_rows = [row for row in ev if row.modality == "behavior"]
    assert {row.sequence_no for row in behavior_rows} == {0, 1, 2, 3}
    high_value_behavior = next(
        row for row in behavior_rows if row.payload_json["fact_type"] == "HIGH_VALUE_CUSTOMER"
    )
    assert high_value_behavior.payload_json["value"] is True
    assert high_value_behavior.payload_json["calculation_rule"] == "high_value_rule_v1"

    formal_dir = _formal_dir(formal_root)
    expected_files = {
        "manifest.json",
        "checksums.json",
        "cases/demo_case_001.json",
        "cases/demo_case_002.json",
        "assets/demo_case_001/scratch_01.jpg",
        "assets/demo_case_002/scratch_01.jpg",
        "source_filename.txt",
    }
    actual_files = {
        path.relative_to(formal_dir).as_posix()
        for path in formal_dir.rglob("*")
        if path.is_file()
    }
    assert actual_files == expected_files
    assert (formal_dir / "source_filename.txt").read_text(encoding="utf-8") == (
        "demo_batch_v1.zip"
    )


def test_import_from_binary_stream(
    gateway: BatchImportGateway, engine: Engine, formal_root: Path
) -> None:
    result = gateway.import_zip(
        io.BytesIO(make_zip(make_entries())), source_filename="stream.zip", trace_id=TRACE
    )
    assert result.ok
    assert result.imported
    assert result.evidence_count == 14
    assert result.source_filename == "stream.zip"
    assert _counts(engine) == (1, 1, 2, 14)


# ---------- 幂等与冲突 ----------


def test_same_package_returns_existing_batch(
    gateway: BatchImportGateway, engine: Engine, formal_root: Path
) -> None:
    raw = make_zip(make_entries())
    first = gateway.import_zip(raw, source_filename="first.zip", trace_id="trace-1")
    assert first.ok and first.imported

    second = gateway.import_zip(raw, source_filename="second.zip", trace_id="trace-2")
    assert second.ok
    assert second.returned_existing and not second.imported
    assert second.batch_id == DEMO_BATCH_ID
    assert second.package_sha256 == first.package_sha256
    assert second.evidence_count == 14
    assert second.case_count == 2
    assert second.trace_id == "trace-2"
    # source_filename 从已保存包文件名读取，而非本次上传名（规格 12.2）
    assert second.source_filename == "first.zip"

    assert _counts(engine) == (1, 1, 2, 14)
    formal_dir = _formal_dir(formal_root)
    file_count = sum(1 for path in formal_dir.rglob("*") if path.is_file())
    assert file_count == 7


def test_concurrent_same_package_keeps_formal_files(
    gateway: BatchImportGateway, formal_root: Path
) -> None:
    """同一应用实例的并发重复上传只能有一次发布，不能删掉成功包目录。"""
    raw = make_zip(make_entries())
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _unused: gateway.import_zip(raw), range(2)))

    assert all(result.ok for result in results)
    assert sum(result.imported for result in results) == 1
    assert sum(result.returned_existing for result in results) == 1
    formal_dir = _formal_dir(formal_root)
    assert (formal_dir / "manifest.json").is_file()
    assert (formal_dir / "assets/demo_case_001/scratch_01.jpg").is_file()


def test_same_data_version_reuses_version_row(
    gateway: BatchImportGateway, engine: Engine
) -> None:
    first = gateway.import_zip(make_zip(make_entries()), trace_id=TRACE)
    assert first.ok

    second = gateway.import_zip(
        make_zip(
            make_entries(
                case_builder=_wrapped_case(batch_id="acceptance_batch_v1"),
                manifest_overrides={"batch_id": "acceptance_batch_v1"},
            )
        ),
        trace_id=TRACE,
    )
    assert second.ok and second.imported
    assert second.batch_id == "acceptance_batch_v1"

    assert _counts(engine) == (1, 2, 4, 28)
    data_version_rows = _rows(engine, DataVersion)
    assert len(data_version_rows) == 1
    assert data_version_rows[0].data_version == DEMO_DATA_VERSION


def test_same_batch_id_different_content_conflict(
    gateway: BatchImportGateway, engine: Engine, formal_root: Path
) -> None:
    first = gateway.import_zip(make_zip(make_entries()), trace_id="trace-1")
    assert first.ok

    def altered_case(case_id: str) -> dict:
        payload = make_case(case_id)
        payload["evidence"]["text_items"][0]["text"] = "这是一份内容不同的售后反馈文本"
        return payload

    conflicting = gateway.import_zip(
        make_zip(make_entries(case_builder=altered_case)),
        source_filename="conflict.zip",
        trace_id="trace-conflict",
    )
    rejection = _single_rejection(conflicting)
    assert rejection.code == ImportRejectionCode.BATCH_ID_CONFLICT
    assert rejection.stage == ImportStage.IMPORT
    assert rejection.object_type == "batch"
    assert rejection.object_id == DEMO_BATCH_ID
    assert rejection.trace_id == "trace-conflict"
    assert conflicting.trace_id == "trace-conflict"

    assert _counts(engine) == (1, 1, 2, 14)
    assert sorted(path.name for path in (formal_root / "batches").glob("*")) == [DEMO_BATCH_ID]


# ---------- 故障回滚 ----------


def test_file_write_failure_leaves_no_semifinished_state(
    gateway: BatchImportGateway, engine: Engine, formal_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(_temp_dir, _formal_dir, _source_filename) -> None:
        raise OSError("磁盘写入失败")

    monkeypatch.setattr(gateway, "_write_formal_package", boom)
    result = gateway.import_zip(make_zip(make_entries()), trace_id="trace-file")

    rejection = _single_rejection(result)
    assert rejection.code == ImportRejectionCode.INTERNAL_ERROR
    assert rejection.stage == ImportStage.IMPORT
    assert rejection.trace_id == "trace-file"
    assert not (formal_root / "batches" / DEMO_BATCH_ID).exists()
    assert _counts(engine) == (0, 0, 0, 0)


def test_transaction_failure_rolls_back_workspace(
    gateway: BatchImportGateway, engine: Engine, formal_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(**kwargs) -> None:
        raise IntegrityError("INSERT INTO batches", {}, Exception("UNIQUE constraint failed"))

    monkeypatch.setattr(gateway.repository, "persist_import", boom)
    result = gateway.import_zip(make_zip(make_entries()), trace_id="trace-tx")

    rejection = _single_rejection(result)
    assert rejection.code == ImportRejectionCode.INTERNAL_ERROR
    assert rejection.stage == ImportStage.IMPORT
    assert rejection.trace_id == "trace-tx"
    assert not (formal_root / "batches" / DEMO_BATCH_ID).exists()
    assert _counts(engine) == (0, 0, 0, 0)


# ---------- 拒绝契约 ----------


def test_bad_zip_rejections_forwarded_with_trace(
    gateway: BatchImportGateway, engine: Engine, formal_root: Path
) -> None:
    result = gateway.import_zip(b"not-a-zip", source_filename="bad.zip", trace_id="trace-bad")

    assert not result.ok
    assert result.trace_id == "trace-bad"
    assert len(result.rejections) == 1
    assert result.rejections[0].code == ImportRejectionCode.INVALID_ZIP
    assert result.rejections[0].stage == ImportStage.ZIP_STRUCTURE
    assert result.rejections[0].trace_id == "trace-bad"
    assert not (formal_root / "batches").exists()
    assert _counts(engine) == (0, 0, 0, 0)


def test_content_length_over_limit_rejected(
    engine: Engine, formal_root: Path, tmp_root: Path
) -> None:
    small = BatchImportGateway(
        engine=engine, formal_root=formal_root, tmp_root=tmp_root, max_zip_bytes=10
    )
    result = small.import_zip(
        make_zip(make_entries()), content_length=100, trace_id="trace-size"
    )
    rejection = _single_rejection(result)
    assert rejection.code == ImportRejectionCode.UPLOAD_TOO_LARGE
    assert rejection.stage == ImportStage.IMPORT
    assert rejection.object_type == "upload"
    assert rejection.trace_id == "trace-size"
    assert _counts(engine) == (0, 0, 0, 0)


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("batch_id", "a/b"),
        ("batch_id", ".."),
        ("data_version", "a/b"),
    ],
)
def test_unsafe_dir_component_rejected(
    gateway: BatchImportGateway,
    engine: Engine,
    formal_root: Path,
    field: str,
    bad_value: str,
) -> None:
    overrides: dict[str, object] = {
        "batch_id": DEMO_BATCH_ID,
        "data_version": DEMO_DATA_VERSION,
    }
    overrides[field] = bad_value
    wrapped = (
        {"batch_id": bad_value} if field == "batch_id" else {"data_version": bad_value}
    )
    result = gateway.import_zip(
        make_zip(
            make_entries(
                case_builder=_wrapped_case(**wrapped), manifest_overrides=overrides
            )
        ),
        trace_id="trace-safe",
    )

    rejection = _single_rejection(result)
    assert rejection.code == ImportRejectionCode.INPUT_CONTRACT_INVALID
    assert rejection.stage == ImportStage.IMPORT
    assert rejection.object_id == f"manifest.json/{field}"
    assert rejection.trace_id == "trace-safe"
    assert not (formal_root / "batches").exists()
    assert _counts(engine) == (0, 0, 0, 0)
