"""M3-08 真实 M1 装配端到端：真实 ZIP 导入读回、状态写入与恢复。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "contracts" / "data_ports"))

import pytest
from zip_fixtures import make_entries, make_zip

from app.modules.application.wiring import build_runtime


@pytest.fixture()
def runtime(tmp_path: Path):
    rt = build_runtime(tmp_path / "runtime_data")
    try:
        yield rt
    finally:
        rt.engine.dispose()


def test_real_zip_import_and_read_back(runtime) -> None:
    entries = make_entries(case_ids=("mvp_case_001",))
    package = make_zip(entries)

    result = runtime.importer.import_zip(
        package, source_filename="mvp.zip", content_length=len(package)
    )
    assert result.ok, result.rejections
    assert result.imported is True
    assert result.case_count == 1
    assert result.is_mock is True

    batches = runtime.query.list_batches(limit=10, offset=0)
    assert batches.total == 1
    batch = runtime.query.get_batch(result.batch_id)
    assert batch.batch_id == result.batch_id
    assert batch.source_filename == "mvp.zip"
    assert batch.case_count == 1
    assert batch.evidence_count > 0

    queue = runtime.query.list_cases(result.batch_id, limit=10, offset=0)
    assert queue.total == 1
    detail = runtime.query.get_case_detail(result.batch_id, queue.items[0].case_id)
    assert detail.batch_id == result.batch_id
    assert detail.is_high_value is True
    assert detail.can_review is False


def test_duplicate_reimport_is_idempotent(runtime) -> None:
    entries = make_entries(case_ids=("mvp_case_001",))
    package = make_zip(entries)
    first = runtime.importer.import_zip(package, source_filename="a.zip")
    assert first.imported is True
    second = runtime.importer.import_zip(package, source_filename="a.zip")
    assert second.returned_existing is True
    assert second.batch_id == first.batch_id


def test_recover_interrupted_is_idempotent(runtime) -> None:
    first = runtime.run_store.recover_interrupted()
    second = runtime.run_store.recover_interrupted()
    assert first.interrupted_case_runs == 0
    assert second.interrupted_case_runs == 0
