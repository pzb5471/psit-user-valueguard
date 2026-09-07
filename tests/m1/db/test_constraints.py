"""M1-02 约束强制测试：外键、唯一约束、枚举 CHECK 与活动运行部分唯一索引。

对应技术实施规格 10.1（数据库唯一约束是最终保护）、11.1（唯一性）与
ADR-0036（Python 枚举和数据库 CHECK 共同约束）。所有用例都在真实迁移出的
SQLite 库上执行，并开启 PRAGMA foreign_keys=ON（规格 11.2 保存规则）。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError

from app.modules.data.db.models import Base

UTC_NOW = datetime.now(UTC)


def _insert(conn: Connection, table_name: str, values: dict[str, Any]) -> int:
    result = conn.execute(Base.metadata.tables[table_name].insert().values(**values))
    pk = result.inserted_primary_key
    assert pk is not None, table_name
    return int(pk[0])


def _update(conn: Connection, table_name: str, row_id: int, **updates: Any) -> None:
    assignments = ", ".join(f"{name} = :{name}" for name in updates)
    conn.execute(
        text(f"UPDATE {table_name} SET {assignments} WHERE id = :row_id"),
        {**updates, "row_id": row_id},
    )


def _expect_integrity_error(conn: Connection, action: Callable[[], Any]) -> None:
    with pytest.raises(IntegrityError):
        with conn.begin_nested():
            action()


def data_version_row(*, data_version: str = "dv-1") -> dict[str, Any]:
    return {
        "data_version": data_version,
        "source_snapshot_ref": "snapshot/001",
        "source_manifest_sha256": "a" * 64,
        "provenance_json": {"package": "demo"},
        "created_at": UTC_NOW,
    }


def batch_row(*, batch_id: str = "b1", data_version_id: int) -> dict[str, Any]:
    return {
        "batch_id": batch_id,
        "data_version_id": data_version_id,
        "schema_version": "case_input_v1",
        "package_sha256": "b" * 64,
        "package_relative_path": f"batches/{batch_id}/manifest.json",
        "status": "COMPLETED",
        "case_count": 1,
        "analysis_succeeded_count": 0,
        "error_count": 0,
        "imported_at": UTC_NOW,
        "updated_at": UTC_NOW,
    }


def case_row(*, batch_id: int, case_id: str = "c1") -> dict[str, Any]:
    return {
        "batch_id": batch_id,
        "case_id": case_id,
        "schema_version": "case_input_v1",
        "case_input_json": {"customer": "demo"},
        "customer_display_id": "cust-1",
        "is_high_value": True,
        "status": "PENDING_ANALYSIS",
        "imported_at": UTC_NOW,
        "updated_at": UTC_NOW,
    }


def evidence_row(*, case_id: int, evidence_id: str = "e1") -> dict[str, Any]:
    return {
        "case_id": case_id,
        "evidence_id": evidence_id,
        "modality": "text",
        "sequence_no": 1,
        "identity": "ev-1",
        "relation_identity": "ev-1",
        "source_ref_json": {"ref": "x"},
        "content_hash": "c" * 64,
        "relative_path": "evidence/e1.txt",
        "media_type": "text/plain",
        "payload_json": {"kind": "text"},
    }


def batch_run_row(*, run_id: str = "br-1", batch_id: int, status: str) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "batch_id": batch_id,
        "status": status,
        "total_case_count": 1,
        "analysis_succeeded_count": 1,
        "error_count": 0,
        "started_at": UTC_NOW,
        "updated_at": UTC_NOW,
    }


def case_run_row(
    *,
    run_id: str = "cr-1",
    case_id: int,
    status: str = "SUCCEEDED",
    trigger_type: str = "BATCH",
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "case_id": case_id,
        "trigger_type": trigger_type,
        "status": status,
        "started_at": UTC_NOW,
        "created_at": UTC_NOW,
        "updated_at": UTC_NOW,
    }


def stage_result_row(*, case_run_id: int, stage_name: str = "perception") -> dict[str, Any]:
    return {
        "case_run_id": case_run_id,
        "stage_name": stage_name,
        "contract_version": "perception_v1",
        "result_json": {"ok": True},
        "result_sha256": "d" * 64,
        "created_at": UTC_NOW,
    }


def model_call_row(*, call_id: str = "mc-1", case_run_id: int) -> dict[str, Any]:
    return {
        "call_id": call_id,
        "case_run_id": case_run_id,
        "stage_name": "perception",
        "attempt_no": 1,
        "model_name": "glm-5.3-flash",
        "prompt_version": "perception_v1",
        "request_manifest_json": {"prompt": "..."},
        "status": "OK",
        "started_at": UTC_NOW,
    }


def review_row(
    *,
    review_id: str = "rv-1",
    submission_id: str = "sb-1",
    case_id: int,
    case_run_id: int,
) -> dict[str, Any]:
    return {
        "review_id": review_id,
        "submission_id": submission_id,
        "case_id": case_id,
        "case_run_id": case_run_id,
        "outcome": "APPROVED",
        "final_intervention_level": "MUST_INTERVENE",
        "final_cause_json": {"risk": "refund"},
        "final_actions_json": [{"action_code": "CUSTOMER_CONTACT"}],
        "created_at": UTC_NOW,
    }


def _seed_batch(conn: Connection, *, batch_id: str = "b1") -> tuple[int, int]:
    # 每个批次用独立 data_version，避免跨 seed 撞 data_version 全局唯一。
    data_version_id = _insert(
        conn, "data_versions", data_version_row(data_version=f"dv-{batch_id}")
    )
    batch_pk = _insert(
        conn, "batches", batch_row(data_version_id=data_version_id, batch_id=batch_id)
    )
    return data_version_id, batch_pk


def _seed_case(conn: Connection, *, batch_id: str = "b1", case_id: str = "c1") -> tuple[int, int]:
    _, batch_pk = _seed_batch(conn, batch_id=batch_id)
    case_pk = _insert(conn, "cases", case_row(batch_id=batch_pk, case_id=case_id))
    return batch_pk, case_pk


def _seed_succeeded_case_run(conn: Connection) -> tuple[int, int]:
    _, case_pk = _seed_case(conn)
    case_run_pk = _insert(conn, "case_runs", case_run_row(run_id="cr-1", case_id=case_pk))
    return case_pk, case_run_pk


# ---------------- 外键 ----------------

def test_fk_batches_requires_data_version(conn: Connection) -> None:
    _expect_integrity_error(
        conn, lambda: _insert(conn, "batches", batch_row(data_version_id=999))
    )


def test_fk_cases_requires_batch(conn: Connection) -> None:
    _expect_integrity_error(conn, lambda: _insert(conn, "cases", case_row(batch_id=999)))


def test_fk_evidence_requires_case(conn: Connection) -> None:
    _expect_integrity_error(conn, lambda: _insert(conn, "evidence", evidence_row(case_id=999)))


def test_fk_batch_run_requires_batch(conn: Connection) -> None:
    _expect_integrity_error(
        conn,
        lambda: _insert(conn, "batch_runs", batch_run_row(batch_id=999, status="RUNNING")),
    )


def test_fk_case_run_requires_case(conn: Connection) -> None:
    _expect_integrity_error(
        conn,
        lambda: _insert(conn, "case_runs", case_run_row(case_id=999, status="SUCCEEDED")),
    )


def test_fk_stage_result_requires_case_run(conn: Connection) -> None:
    _expect_integrity_error(
        conn, lambda: _insert(conn, "stage_results", stage_result_row(case_run_id=999))
    )


def test_fk_model_call_requires_case_run(conn: Connection) -> None:
    _expect_integrity_error(
        conn, lambda: _insert(conn, "model_calls", model_call_row(case_run_id=999))
    )


def test_fk_review_requires_case_and_case_run(conn: Connection) -> None:
    _expect_integrity_error(
        conn, lambda: _insert(conn, "reviews", review_row(case_id=999, case_run_id=1))
    )


# ---------------- 唯一约束 ----------------

def test_unique_data_version(conn: Connection) -> None:
    _insert(conn, "data_versions", data_version_row())
    _expect_integrity_error(conn, lambda: _insert(conn, "data_versions", data_version_row()))


def test_unique_batch_id(conn: Connection) -> None:
    dv1 = _insert(conn, "data_versions", data_version_row(data_version="dv-a"))
    dv2 = _insert(conn, "data_versions", data_version_row(data_version="dv-b"))
    _insert(conn, "batches", batch_row(batch_id="b1", data_version_id=dv1))
    _expect_integrity_error(
        conn, lambda: _insert(conn, "batches", batch_row(batch_id="b1", data_version_id=dv2))
    )


def test_unique_case_id_within_batch(conn: Connection) -> None:
    _, batch_pk = _seed_batch(conn)
    _insert(conn, "cases", case_row(batch_id=batch_pk, case_id="c1"))
    _expect_integrity_error(
        conn, lambda: _insert(conn, "cases", case_row(batch_id=batch_pk, case_id="c1"))
    )


def test_same_case_id_allowed_in_different_batch(conn: Connection) -> None:
    _, batch1 = _seed_batch(conn, batch_id="b1")
    _, batch2 = _seed_batch(conn, batch_id="b2")
    _insert(conn, "cases", case_row(batch_id=batch1, case_id="c1"))
    _insert(conn, "cases", case_row(batch_id=batch2, case_id="c1"))  # 不报错


def test_unique_evidence_id_within_case(conn: Connection) -> None:
    _, case_pk = _seed_case(conn)
    _insert(conn, "evidence", evidence_row(case_id=case_pk, evidence_id="e1"))
    _expect_integrity_error(
        conn,
        lambda: _insert(conn, "evidence", evidence_row(case_id=case_pk, evidence_id="e1")),
    )


def test_same_evidence_id_allowed_in_different_case(conn: Connection) -> None:
    _, case1 = _seed_case(conn, case_id="c1")
    _, case2 = _seed_case(conn, batch_id="b2", case_id="c2")
    _insert(conn, "evidence", evidence_row(case_id=case1, evidence_id="e1"))
    _insert(conn, "evidence", evidence_row(case_id=case2, evidence_id="e1"))  # 不报错


def test_unique_batch_run_run_id(conn: Connection) -> None:
    _, batch_pk = _seed_batch(conn)
    _insert(
        conn,
        "batch_runs",
        batch_run_row(run_id="br-1", batch_id=batch_pk, status="COMPLETED"),
    )
    _expect_integrity_error(
        conn,
        lambda: _insert(
            conn, "batch_runs", batch_run_row(run_id="br-1", batch_id=batch_pk, status="FAILED")
        ),
    )


def test_unique_case_run_run_id(conn: Connection) -> None:
    _, case_pk = _seed_case(conn)
    _insert(conn, "case_runs", case_run_row(run_id="cr-1", case_id=case_pk))
    _expect_integrity_error(
        conn, lambda: _insert(conn, "case_runs", case_run_row(run_id="cr-1", case_id=case_pk))
    )


def test_unique_stage_result_per_case_run_and_stage(conn: Connection) -> None:
    _, case_run_pk = _seed_succeeded_case_run(conn)
    _insert(
        conn,
        "stage_results",
        stage_result_row(case_run_id=case_run_pk, stage_name="perception"),
    )
    _expect_integrity_error(
        conn,
        lambda: _insert(
            conn,
            "stage_results",
            stage_result_row(case_run_id=case_run_pk, stage_name="perception"),
        ),
    )
    _insert(
        conn,
        "stage_results",
        stage_result_row(case_run_id=case_run_pk, stage_name="attribution"),
    )


def test_unique_model_call_call_id(conn: Connection) -> None:
    _, case_run_pk = _seed_succeeded_case_run(conn)
    _insert(conn, "model_calls", model_call_row(call_id="mc-1", case_run_id=case_run_pk))
    _expect_integrity_error(
        conn,
        lambda: _insert(
            conn, "model_calls", model_call_row(call_id="mc-1", case_run_id=case_run_pk)
        ),
    )


def test_unique_review_review_id(conn: Connection) -> None:
    _, case_pk = _seed_case(conn)
    case_run_pk = _insert(conn, "case_runs", case_run_row(run_id="cr-1", case_id=case_pk))
    _insert(
        conn, "reviews", review_row(review_id="rv-1", case_id=case_pk, case_run_id=case_run_pk)
    )
    _expect_integrity_error(
        conn,
        lambda: _insert(
            conn,
            "reviews",
            review_row(
                review_id="rv-1", submission_id="sb-2", case_id=case_pk, case_run_id=case_run_pk
            ),
        ),
    )


def test_unique_review_submission_id(conn: Connection) -> None:
    _, case_pk = _seed_case(conn)
    case_run_pk = _insert(conn, "case_runs", case_run_row(run_id="cr-1", case_id=case_pk))
    _insert(
        conn, "reviews", review_row(review_id="rv-1", case_id=case_pk, case_run_id=case_run_pk)
    )
    _expect_integrity_error(
        conn,
        lambda: _insert(
            conn,
            "reviews",
            review_row(
                review_id="rv-2", submission_id="sb-1", case_id=case_pk, case_run_id=case_run_pk
            ),
        ),
    )


def test_unique_review_per_case(conn: Connection) -> None:
    _, case_pk = _seed_case(conn)
    case_run_pk = _insert(conn, "case_runs", case_run_row(run_id="cr-1", case_id=case_pk))
    _insert(
        conn, "reviews", review_row(review_id="rv-1", case_id=case_pk, case_run_id=case_run_pk)
    )
    _expect_integrity_error(
        conn,
        lambda: _insert(
            conn,
            "reviews",
            review_row(
                review_id="rv-2", submission_id="sb-2", case_id=case_pk, case_run_id=case_run_pk
            ),
        ),
    )


# ---------------- 枚举 CHECK ----------------

def test_check_rejects_invalid_batch_status(conn: Connection) -> None:
    data_version_id = _insert(conn, "data_versions", data_version_row())
    batch_pk = _insert(conn, "batches", batch_row(data_version_id=data_version_id))
    _expect_integrity_error(conn, lambda: _update(conn, "batches", batch_pk, status="BOGUS"))


def test_check_rejects_invalid_case_status(conn: Connection) -> None:
    _, case_pk = _seed_case(conn)
    _expect_integrity_error(conn, lambda: _update(conn, "cases", case_pk, status="BOGUS"))


def test_check_rejects_invalid_case_intervention_level(conn: Connection) -> None:
    _, case_pk = _seed_case(conn)
    _expect_integrity_error(
        conn, lambda: _update(conn, "cases", case_pk, system_intervention_level="BOGUS")
    )


def test_check_rejects_invalid_batch_run_status(conn: Connection) -> None:
    _, batch_pk = _seed_batch(conn)
    run_pk = _insert(conn, "batch_runs", batch_run_row(batch_id=batch_pk, status="COMPLETED"))
    _expect_integrity_error(conn, lambda: _update(conn, "batch_runs", run_pk, status="BOGUS"))


def test_check_rejects_invalid_case_run_status(conn: Connection) -> None:
    _, case_pk = _seed_case(conn)
    run_pk = _insert(conn, "case_runs", case_run_row(case_id=case_pk))
    _expect_integrity_error(conn, lambda: _update(conn, "case_runs", run_pk, status="BOGUS"))


def test_check_rejects_invalid_trigger_type(conn: Connection) -> None:
    _, case_pk = _seed_case(conn)
    run_pk = _insert(conn, "case_runs", case_run_row(case_id=case_pk))
    _expect_integrity_error(conn, lambda: _update(conn, "case_runs", run_pk, trigger_type="BOGUS"))


def test_check_rejects_invalid_review_outcome(conn: Connection) -> None:
    case_pk, case_run_pk = _seed_succeeded_case_run(conn)
    review_pk = _insert(conn, "reviews", review_row(case_id=case_pk, case_run_id=case_run_pk))
    _expect_integrity_error(conn, lambda: _update(conn, "reviews", review_pk, outcome="BOGUS"))


def test_check_rejects_invalid_review_intervention_level(conn: Connection) -> None:
    case_pk, case_run_pk = _seed_succeeded_case_run(conn)
    review_pk = _insert(conn, "reviews", review_row(case_id=case_pk, case_run_id=case_run_pk))
    _expect_integrity_error(
        conn, lambda: _update(conn, "reviews", review_pk, final_intervention_level="BOGUS")
    )


# ---------------- 活动运行约束（部分唯一索引） ----------------

def test_two_active_batch_runs_rejected(conn: Connection) -> None:
    _, batch_pk = _seed_batch(conn)
    _insert(
        conn,
        "batch_runs",
        batch_run_row(run_id="br-1", batch_id=batch_pk, status="RUNNING"),
    )
    _expect_integrity_error(
        conn,
        lambda: _insert(
            conn,
            "batch_runs",
            batch_run_row(run_id="br-2", batch_id=batch_pk, status="STARTING"),
        ),
    )


def test_finished_batch_runs_can_coexist(conn: Connection) -> None:
    _, batch_pk = _seed_batch(conn)
    _insert(
        conn,
        "batch_runs",
        batch_run_row(run_id="br-1", batch_id=batch_pk, status="COMPLETED"),
    )
    _insert(
        conn,
        "batch_runs",
        batch_run_row(run_id="br-2", batch_id=batch_pk, status="FAILED"),
    )


def test_finishing_active_batch_run_allows_next(conn: Connection) -> None:
    _, batch_pk = _seed_batch(conn)
    first_pk = _insert(
        conn,
        "batch_runs",
        batch_run_row(run_id="br-1", batch_id=batch_pk, status="RUNNING"),
    )
    _update(conn, "batch_runs", first_pk, status="COMPLETED")
    _insert(
        conn,
        "batch_runs",
        batch_run_row(run_id="br-2", batch_id=batch_pk, status="STARTING"),
    )


def test_two_active_case_runs_same_case_rejected(conn: Connection) -> None:
    _, case_pk = _seed_case(conn)
    _insert(
        conn,
        "case_runs",
        case_run_row(run_id="cr-1", case_id=case_pk, status="STRATEGY_RUNNING"),
    )
    _expect_integrity_error(
        conn,
        lambda: _insert(
            conn,
            "case_runs",
            case_run_row(run_id="cr-2", case_id=case_pk, status="PERCEPTION_RUNNING"),
        ),
    )


def test_active_case_runs_across_cases_allowed(conn: Connection) -> None:
    _, case1 = _seed_case(conn, case_id="c1")
    _, case2 = _seed_case(conn, batch_id="b2", case_id="c2")
    _insert(
        conn,
        "case_runs",
        case_run_row(run_id="cr-1", case_id=case1, status="STRATEGY_RUNNING"),
    )
    _insert(
        conn,
        "case_runs",
        case_run_row(run_id="cr-2", case_id=case2, status="STRATEGY_RUNNING"),
    )


def test_finished_case_runs_can_coexist(conn: Connection) -> None:
    _, case_pk = _seed_case(conn)
    _insert(conn, "case_runs", case_run_row(run_id="cr-1", case_id=case_pk, status="SUCCEEDED"))
    _insert(conn, "case_runs", case_run_row(run_id="cr-2", case_id=case_pk, status="FAILED"))


def test_finishing_active_case_run_allows_next(conn: Connection) -> None:
    _, case_pk = _seed_case(conn)
    first_pk = _insert(
        conn,
        "case_runs",
        case_run_row(run_id="cr-1", case_id=case_pk, status="ATTRIBUTION_RUNNING"),
    )
    _update(conn, "case_runs", first_pk, status="SUCCEEDED")
    _insert(
        conn,
        "case_runs",
        case_run_row(run_id="cr-2", case_id=case_pk, status="STARTING"),
    )
