"""M1-05：CaseQueryGateway 与当前投影测试（技术实施规格 8/10.3/12.1/12.2）。

覆盖查询网关的稳定业务投影：

- 批次：imported_at 倒序 + batch_id 升序稳定排序、分页与 limit/offset 校验；
- 批次状态/三项计数从当前案例 + 当前 case_run 实时聚合（规格 10.3），
  can_start_analysis 受全系统活动 batch_run 约束；
- 案例队列：固定等级排序（1/2/3，NULL 最后）、单个 status/介入等级筛选、
  三个标记从结果 JSON 约定键读取、证据/图片类技术失败置 modality 标记；
- 案例详情：只投影当前 case_run（与首次历史分离）、review_token 随重跑变化、
  can_rerun/can_review 矩阵、人工确认优先/系统回退、processing_error 业务阶段。

测试直接向迁移出的真实 SQLite 库插入 BatchRun/CaseRun/StageResult/Review 行，
不依赖 M1-07 RunStore（过渡期聚合假设：批次状态与计数实时推导）。
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast

import pytest
from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from zip_fixtures import make_case, make_entries, make_zip

from app.contracts.states import (
    BatchRunStatus,
    BatchStatus,
    CaseRunStatus,
    CaseStatus,
    TriggerType,
)
from app.modules.data.db.models import (
    Batch,
    BatchRun,
    Case,
    CaseRun,
    InterventionLevel,
    Review,
    ReviewOutcome,
    StageResult,
)
from app.modules.data.queries.gateway import _run_flags
from app.modules.data.queries.views import (
    BatchWorkspaceView,
    CaseDetailView,
    CaseQueueItemView,
    build_review_options,
)

DEFAULT_RISK_SUMMARY = "高价值风险待处理"
DEFAULT_PRIORITY_REASON = "高价值客户且商品问题明确"


# ---------- 测试构造助手 ----------

def _wrapped_case(*, batch_id: str) -> Callable[[str], dict[str, Any]]:
    """改写案例 JSON 的 batch_id，配合 manifest_overrides 导入多批次。"""

    def builder(case_id: str) -> dict[str, Any]:
        payload = make_case(case_id)
        payload["batch_id"] = batch_id
        return payload

    return builder


def _import_batch(
    gateway,
    *,
    batch_id: str,
    case_ids: tuple[str, ...] = ("demo_case_001", "demo_case_002"),
    source_filename: str = "upload.zip",
) -> str:
    """导入一个由 zip_fixtures 构造的完整标准 ZIP，返回 batch_id。"""
    entries = make_entries(
        case_ids=case_ids,
        case_builder=_wrapped_case(batch_id=batch_id),
        manifest_overrides={"batch_id": batch_id},
    )
    result = gateway.import_zip(
        make_zip(entries), source_filename=source_filename, trace_id=f"trace-{batch_id}"
    )
    assert result.ok, result
    assert result.batch_id == batch_id
    return batch_id


def _case_row(session: Session, *, batch_id: str, case_id: str) -> Case:
    batch = session.scalar(select(Batch).where(Batch.batch_id == batch_id))
    assert batch is not None, batch_id
    case = session.scalar(
        select(Case).where(Case.batch_id == batch.id, Case.case_id == case_id)
    )
    assert case is not None, f"{batch_id}/{case_id}"
    return case


def _standard_stages(
    *,
    case_id: str = "demo_case_001",
    risk_summary: str = DEFAULT_RISK_SUMMARY,
    intervention_level: str = "MUST_INTERVENE",
    conflict: bool = False,
    insufficient: bool = False,
    modality: bool = False,
    cited_ids: tuple[str, ...] | None = None,
) -> dict[str, dict[str, Any]]:
    """生成 perception/attribution/strategy 三个标准阶段结果（约定键）。"""
    refs = list(cited_ids or ())
    return {
        "perception": {
            "risk_summary": risk_summary,
            "image_observations": [
                {
                    "image_evidence_id": f"ev_image_{case_id}",
                    "observable_facts": ["商品外观有划痕"],
                }
            ],
        },
        "attribution": {
            "primary_cause": {
                "cause_category": "PRODUCT_ISSUE",
                "confidence": 0.9,
            },
            "support_evidence": refs,
            "has_evidence_conflict": conflict,
        },
        "strategy": {
            "intervention_level": intervention_level,
            "priority_reason": DEFAULT_PRIORITY_REASON,
            "actions": [{"action_type": "CUSTOMER_CONTACT", "content": "联系客户"}],
            "communication_points": [{"point": "致歉并说明换货进度"}],
            "execution_note": "已生成沟通要点",
            "has_insufficient_evidence": insufficient,
            "has_modality_failure": modality,
            "uncertainty": ["配送时间不确定"],
            "missing_evidence": ["order_delivery_detail"],
        },
    }


def _complete_current_run(
    engine: Engine,
    *,
    batch_id: str,
    case_id: str,
    run_id: str,
    stages: dict[str, dict[str, Any]],
    status: CaseStatus = CaseStatus.PENDING_REVIEW,
    run_status: CaseRunStatus = CaseRunStatus.SUCCEEDED,
    system_level: InterventionLevel | None = None,
    previous_case_run_id: int | None = None,
    error_code: str | None = None,
    error_stage: str | None = None,
    error_detail_json: dict[str, Any] | None = None,
) -> int:
    """插入一个已结束 case_run + 阶段结果，并设为案例当前投影。"""
    with Session(engine) as session:
        case = _case_row(session, batch_id=batch_id, case_id=case_id)
        now = datetime.now(UTC)
        run = CaseRun(
            run_id=run_id,
            case_id=case.id,
            batch_run_id=None,
            previous_case_run_id=previous_case_run_id,
            trigger_type=(
                TriggerType.MANUAL_RERUN
                if previous_case_run_id is not None
                else TriggerType.BATCH
            ),
            status=run_status,
            current_stage=None,
            error_code=error_code,
            error_stage=error_stage,
            error_detail_json=error_detail_json,
            started_at=now,
            finished_at=now,
            created_at=now,
            updated_at=now,
        )
        session.add(run)
        session.flush()
        for stage_name, result_json in stages.items():
            session.add(
                StageResult(
                    case_run_id=run.id,
                    stage_name=stage_name,
                    contract_version="result.v1",
                    result_json=result_json,
                    result_sha256="a" * 64,
                    created_at=now,
                )
            )
        case.status = status
        case.current_case_run_id = run.id
        if system_level is not None:
            case.system_intervention_level = system_level
        session.commit()
        return run.id


def _update_case(engine: Engine, *, batch_id: str, case_id: str, **values: Any) -> None:
    with Session(engine) as session:
        case = _case_row(session, batch_id=batch_id, case_id=case_id)
        for key, value in values.items():
            setattr(case, key, value)
        session.commit()


def _insert_batch_run(
    engine: Engine, *, batch_id: str, run_id: str, status: BatchRunStatus
) -> int:
    with Session(engine) as session:
        batch = session.scalar(select(Batch).where(Batch.batch_id == batch_id))
        assert batch is not None, batch_id
        now = datetime.now(UTC)
        run = BatchRun(
            run_id=run_id,
            batch_id=batch.id,
            status=status,
            total_case_count=0,
            analysis_succeeded_count=0,
            error_count=0,
            started_at=now,
            finished_at=None,
            updated_at=now,
        )
        session.add(run)
        session.commit()
        return run.id


def _insert_active_case_run(
    engine: Engine, *, batch_id: str, case_id: str, run_id: str
) -> int:
    with Session(engine) as session:
        case = _case_row(session, batch_id=batch_id, case_id=case_id)
        now = datetime.now(UTC)
        run = CaseRun(
            run_id=run_id,
            case_id=case.id,
            batch_run_id=None,
            previous_case_run_id=None,
            trigger_type=TriggerType.MANUAL_RERUN,
            status=CaseRunStatus.PERCEPTION_RUNNING,
            current_stage="perception",
            error_code=None,
            error_stage=None,
            error_detail_json=None,
            started_at=now,
            finished_at=None,
            created_at=now,
            updated_at=now,
        )
        session.add(run)
        session.flush()
        case.current_case_run_id = run.id
        session.commit()
        return run.id


def _insert_review(
    engine: Engine,
    *,
    batch_id: str,
    case_id: str,
    case_run_id: int,
    outcome: ReviewOutcome = ReviewOutcome.APPROVED,
    final_level: InterventionLevel | None = None,
    final_cause: dict[str, Any] | None = None,
    final_actions: list[Any] | None = None,
    review_reason: str | None = None,
    execution_note: str | None = None,
) -> int:
    with Session(engine) as session:
        case = _case_row(session, batch_id=batch_id, case_id=case_id)
        now = datetime.now(UTC)
        review = Review(
            review_id=f"review-{case_id}",
            submission_id=f"submission-{case_id}",
            case_id=case.id,
            case_run_id=case_run_id,
            outcome=outcome,
            final_intervention_level=final_level,
            final_cause_json=final_cause,
            final_actions_json=final_actions,
            review_reason=review_reason,
            execution_note=execution_note,
            created_at=now,
        )
        session.add(review)
        session.flush()
        case.current_review_id = review.id
        case.status = CaseStatus.COMPLETED
        session.commit()
        return review.id


# ---------- 批次列表 ----------

def test_list_batches_empty_defaults(query_gateway) -> None:
    view = query_gateway.list_batches()
    assert view.total == 0
    assert view.items == []


def test_list_batches_sorts_imported_at_desc_then_batch_id_asc(
    query_gateway, gateway, engine
) -> None:
    for batch_id in ("b1", "b2", "b3"):
        _import_batch(gateway, batch_id=batch_id)
    with Session(engine) as session:
        session.execute(
            update(Batch).where(Batch.batch_id == "b1").values(imported_at=datetime(2024, 1, 1))
        )
        session.execute(
            update(Batch).where(Batch.batch_id == "b2").values(imported_at=datetime(2024, 3, 1))
        )
        session.execute(
            update(Batch).where(Batch.batch_id == "b3").values(imported_at=datetime(2024, 5, 1))
        )
        session.commit()
    view = query_gateway.list_batches()
    assert [item.batch_id for item in view.items] == ["b3", "b2", "b1"]
    assert view.total == 3


def test_list_batches_stable_within_same_imported_at(
    query_gateway, gateway, engine
) -> None:
    for batch_id in ("beta", "alpha"):
        _import_batch(gateway, batch_id=batch_id)
    same = datetime(2024, 6, 1, 12, 0, 0)
    with Session(engine) as session:
        session.execute(update(Batch).where(Batch.batch_id == "beta").values(imported_at=same))
        session.execute(update(Batch).where(Batch.batch_id == "alpha").values(imported_at=same))
        session.commit()
    view = query_gateway.list_batches()
    assert [item.batch_id for item in view.items] == ["alpha", "beta"]


def test_list_batches_pagination(query_gateway, gateway, engine) -> None:
    for batch_id in ("p1", "p2", "p3"):
        _import_batch(gateway, batch_id=batch_id)
    with Session(engine) as session:
        session.execute(
            update(Batch).where(Batch.batch_id == "p1").values(imported_at=datetime(2024, 1, 1))
        )
        session.execute(
            update(Batch).where(Batch.batch_id == "p2").values(imported_at=datetime(2024, 2, 1))
        )
        session.execute(
            update(Batch).where(Batch.batch_id == "p3").values(imported_at=datetime(2024, 3, 1))
        )
        session.commit()
    page1 = query_gateway.list_batches(limit=2)
    assert [item.batch_id for item in page1.items] == ["p3", "p2"]
    assert page1.total == 3
    page2 = query_gateway.list_batches(limit=2, offset=2)
    assert [item.batch_id for item in page2.items] == ["p1"]
    assert page2.total == 3


@pytest.mark.parametrize("limit", [0, -1, 101, "5", 1.5, True])
def test_list_batches_rejects_invalid_limit(query_gateway, limit) -> None:
    with pytest.raises(ValueError):
        query_gateway.list_batches(limit=limit)


@pytest.mark.parametrize("offset", [-1, "0", 1.5, True])
def test_list_batches_rejects_invalid_offset(query_gateway, offset) -> None:
    with pytest.raises(ValueError):
        query_gateway.list_batches(offset=offset)


def test_get_batch_missing_raises_lookup_error(query_gateway) -> None:
    with pytest.raises(LookupError):
        query_gateway.get_batch("no-such-batch")


# ---------- 批次详情 / 实时聚合 ----------

def test_batch_workspace_projection(query_gateway, gateway) -> None:
    batch_id = _import_batch(gateway, batch_id="ws", source_filename="customer_demo_v1.zip")
    view = query_gateway.get_batch(batch_id)
    assert isinstance(view, BatchWorkspaceView)
    assert view.batch_id == "ws"
    assert view.source_filename == "customer_demo_v1.zip"
    assert view.is_mock is True
    assert view.status == BatchStatus.PENDING_ANALYSIS.value
    assert view.case_count == 2
    assert view.evidence_count == 14
    assert view.analysis_succeeded_count == 0
    assert view.error_count == 0
    assert "T" in view.imported_at
    listed = query_gateway.list_batches()
    assert listed.total == 1
    assert listed.items[0].evidence_count == 14


def test_batch_status_and_counts_lifecycle(query_gateway, gateway, engine) -> None:
    batch_id = _import_batch(gateway, batch_id="life")
    assert query_gateway.get_batch(batch_id).status == BatchStatus.PENDING_ANALYSIS.value

    # 首次批量运行已结束但案例尚未出结果 → 过渡期 ANALYZING
    _insert_batch_run(
        engine, batch_id=batch_id, run_id="life-br-1", status=BatchRunStatus.COMPLETED
    )
    assert query_gateway.get_batch(batch_id).status == BatchStatus.ANALYZING.value

    # 全部案例具备完整结果 → COMPLETED，分析成功数实时聚合
    _complete_current_run(
        engine,
        batch_id=batch_id,
        case_id="demo_case_001",
        run_id="life-c1",
        status=CaseStatus.PENDING_REVIEW,
        system_level=InterventionLevel.MUST_INTERVENE,
        stages=_standard_stages(),
    )
    _complete_current_run(
        engine,
        batch_id=batch_id,
        case_id="demo_case_002",
        run_id="life-c2",
        status=CaseStatus.COMPLETED,
        system_level=InterventionLevel.SHOULD_INTERVENE,
        stages=_standard_stages(case_id="demo_case_002"),
    )
    view = query_gateway.get_batch(batch_id)
    assert view.status == BatchStatus.COMPLETED.value
    assert view.analysis_succeeded_count == 2
    assert view.error_count == 0

    # 一个案例处理异常 → COMPLETED_WITH_ERRORS
    _complete_current_run(
        engine,
        batch_id=batch_id,
        case_id="demo_case_002",
        run_id="life-c2-fail",
        status=CaseStatus.PROCESSING_ERROR,
        run_status=CaseRunStatus.FAILED,
        error_code="MODEL_TIMEOUT",
        error_stage="strategy",
        stages={},
    )
    view = query_gateway.get_batch(batch_id)
    assert view.status == BatchStatus.COMPLETED_WITH_ERRORS.value
    assert view.analysis_succeeded_count == 1
    assert view.error_count == 1

    # 任一案例处于 ANALYZING 优先 → ANALYZING
    _update_case(
        engine, batch_id=batch_id, case_id="demo_case_001", status=CaseStatus.ANALYZING
    )
    assert query_gateway.get_batch(batch_id).status == BatchStatus.ANALYZING.value


def test_batch_can_start_analysis_flow(query_gateway, gateway, engine) -> None:
    batch_id = _import_batch(gateway, batch_id="start")
    assert query_gateway.get_batch(batch_id).can_start_analysis is True

    # 全系统存在活动 batch_run 时禁止再次开始
    _insert_batch_run(
        engine, batch_id=batch_id, run_id="start-br", status=BatchRunStatus.STARTING
    )
    assert query_gateway.get_batch(batch_id).can_start_analysis is False

    # 案例已进入 ANALYZING 同样禁止开始
    batch2 = _import_batch(gateway, batch_id="start2")
    _update_case(
        engine, batch_id=batch2, case_id="demo_case_001", status=CaseStatus.ANALYZING
    )
    assert query_gateway.get_batch(batch2).can_start_analysis is False


# ---------- 案例队列 ----------

def test_queue_orders_by_level_then_imported_at_then_case_id(
    query_gateway, gateway, engine
) -> None:
    batch_id = _import_batch(
        gateway,
        batch_id="qord",
        case_ids=("rank1a", "rank1b", "rank2", "rank3", "nullcase"),
    )
    base = datetime(2024, 1, 1, 0, 0, 0)
    with Session(engine) as session:
        for case_id, (offset_seconds, level) in {
            "nullcase": (-1, None),
            "rank2": (1, InterventionLevel.SHOULD_INTERVENE),
            "rank3": (0, InterventionLevel.NO_IMMEDIATE_INTERVENTION),
            "rank1a": (2, InterventionLevel.MUST_INTERVENE),
            "rank1b": (2, InterventionLevel.MUST_INTERVENE),
        }.items():
            batch = session.scalar(select(Batch).where(Batch.batch_id == batch_id))
            assert batch is not None
            case = session.scalar(
                select(Case).where(Case.batch_id == batch.id, Case.case_id == case_id)
            )
            assert case is not None
            case.system_intervention_level = level
            case.imported_at = base + timedelta(seconds=offset_seconds)
        session.commit()
    view = query_gateway.list_cases(batch_id)
    assert [item.case_id for item in view.items] == [
        "rank1a",
        "rank1b",
        "rank2",
        "rank3",
        "nullcase",
    ]
    assert view.total == 5
    by_id = {item.case_id: item for item in view.items}
    assert by_id["rank1a"].intervention_level == "MUST_INTERVENE"
    assert by_id["nullcase"].intervention_level is None


def test_queue_status_filter(query_gateway, gateway, engine) -> None:
    batch_id = _import_batch(gateway, batch_id="qsf", case_ids=("c1", "c2", "c3"))
    _complete_current_run(
        engine,
        batch_id=batch_id,
        case_id="c1",
        run_id="qsf-c1",
        status=CaseStatus.COMPLETED,
        stages=_standard_stages(case_id="c1"),
    )
    _complete_current_run(
        engine,
        batch_id=batch_id,
        case_id="c2",
        run_id="qsf-c2",
        status=CaseStatus.PENDING_REVIEW,
        stages=_standard_stages(case_id="c2"),
    )
    pending = query_gateway.list_cases(batch_id, status="PENDING_REVIEW")
    assert [item.case_id for item in pending.items] == ["c2"]
    assert pending.total == 1
    done = query_gateway.list_cases(batch_id, status="COMPLETED")
    assert [item.case_id for item in done.items] == ["c1"]
    assert query_gateway.list_cases(batch_id, status="PENDING_ANALYSIS").total == 1


def test_queue_intervention_level_filter(query_gateway, gateway, engine) -> None:
    batch_id = _import_batch(gateway, batch_id="qlf", case_ids=("c1", "c2", "c3"))
    _update_case(
        engine,
        batch_id=batch_id,
        case_id="c1",
        system_intervention_level=InterventionLevel.MUST_INTERVENE,
        final_intervention_level=InterventionLevel.SHOULD_INTERVENE,
    )
    _update_case(
        engine,
        batch_id=batch_id,
        case_id="c2",
        system_intervention_level=InterventionLevel.SHOULD_INTERVENE,
    )
    _update_case(
        engine,
        batch_id=batch_id,
        case_id="c3",
        system_intervention_level=InterventionLevel.MUST_INTERVENE,
    )
    view = query_gateway.list_cases(batch_id, intervention_level="SHOULD_INTERVENE")
    assert [item.case_id for item in view.items] == ["c1", "c2"]
    assert view.total == 2
    must = query_gateway.list_cases(batch_id, intervention_level="MUST_INTERVENE")
    assert [item.case_id for item in must.items] == ["c3"]


def test_queue_flags_from_result_json_and_technical_failure(
    query_gateway, gateway, engine
) -> None:
    batch_id = _import_batch(gateway, batch_id="qflg", case_ids=("c1", "c2", "c3"))
    _complete_current_run(
        engine,
        batch_id=batch_id,
        case_id="c1",
        run_id="qflg-c1",
        status=CaseStatus.PENDING_REVIEW,
        system_level=InterventionLevel.MUST_INTERVENE,
        stages=_standard_stages(case_id="c1", conflict=True),
    )
    _complete_current_run(
        engine,
        batch_id=batch_id,
        case_id="c2",
        run_id="qflg-c2",
        status=CaseStatus.PENDING_REVIEW,
        system_level=InterventionLevel.SHOULD_INTERVENE,
        stages=_standard_stages(case_id="c2", insufficient=True),
    )
    _complete_current_run(
        engine,
        batch_id=batch_id,
        case_id="c3",
        run_id="qflg-c3",
        status=CaseStatus.PROCESSING_ERROR,
        run_status=CaseRunStatus.FAILED,
        error_code="EVIDENCE_MEDIA_INVALID",
        error_stage="perception",
        stages={},
    )
    view = query_gateway.list_cases(batch_id)
    by_id = {item.case_id: item for item in view.items}
    assert by_id["c1"].has_evidence_conflict is True
    assert by_id["c1"].has_insufficient_evidence is False
    assert by_id["c2"].has_insufficient_evidence is True
    assert by_id["c3"].has_modality_failure is True
    assert by_id["c3"].has_evidence_conflict is False
    assert by_id["c1"].risk_summary == DEFAULT_RISK_SUMMARY
    assert by_id["c1"].priority_reason == DEFAULT_PRIORITY_REASON


def test_queue_flags_derive_from_frozen_result_contract() -> None:
    """冲突、缺口和证据不足不依赖合同外的 has_* 布尔字段。"""
    results = [
        SimpleNamespace(
            stage_name="perception",
            result_json={
                "events": [{"conflicting_evidence": ["ev_image_demo_case_001"]}],
                "image_observations": [
                    {"relationship": "CONFLICTS"},
                ],
                "missing_evidence": ["order_delivery_detail"],
            }
        ),
        SimpleNamespace(
            stage_name="attribution",
            result_json={
                "primary_cause": {"cause_category": "INSUFFICIENT_EVIDENCE"}
            }
        ),
    ]

    assert _run_flags(cast(list[StageResult], results), None) == (True, True, False)


def test_queue_pagination_and_default_limit(query_gateway, gateway) -> None:
    batch_id = _import_batch(
        gateway, batch_id="qpage", case_ids=("c1", "c2", "c3", "c4", "c5")
    )
    first = query_gateway.list_cases(batch_id, limit=2)
    assert [item.case_id for item in first.items] == ["c1", "c2"]
    assert first.total == 5
    rest = query_gateway.list_cases(batch_id, limit=2, offset=2)
    assert [item.case_id for item in rest.items] == ["c3", "c4"]
    assert rest.total == 5


def test_list_cases_missing_batch_raises_lookup_error(query_gateway) -> None:
    with pytest.raises(LookupError):
        query_gateway.list_cases("no-such-batch")


@pytest.mark.parametrize("status", ["NOPE", ""])
def test_queue_rejects_invalid_status_filter(query_gateway, status) -> None:
    with pytest.raises(ValueError):
        query_gateway.list_cases("any-batch", status=status)


@pytest.mark.parametrize("level", ["NOPE", "INSUFFICIENT_EVIDENCE"])
def test_queue_rejects_invalid_level_filter(query_gateway, level) -> None:
    with pytest.raises(ValueError):
        query_gateway.list_cases("any-batch", intervention_level=level)


@pytest.mark.parametrize("limit", [0, 101, "5", True])
def test_queue_rejects_invalid_limit(query_gateway, limit) -> None:
    with pytest.raises(ValueError):
        query_gateway.list_cases("any-batch", limit=limit)


# ---------- 案例详情 ----------

def test_case_detail_missing_batch_or_case_raises(query_gateway, gateway) -> None:
    batch_id = _import_batch(gateway, batch_id="miss")
    with pytest.raises(LookupError):
        query_gateway.get_case_detail("no-such-batch", "demo_case_001")
    with pytest.raises(LookupError):
        query_gateway.get_case_detail(batch_id, "no-such-case")


def test_case_detail_full_projection(query_gateway, gateway, engine) -> None:
    batch_id = _import_batch(gateway, batch_id="detail")
    _complete_current_run(
        engine,
        batch_id=batch_id,
        case_id="demo_case_001",
        run_id="detail-run-1",
        status=CaseStatus.PENDING_REVIEW,
        system_level=InterventionLevel.MUST_INTERVENE,
        stages=_standard_stages(
            cited_ids=("ev_text_demo_case_001_1", "ev_behavior_demo_case_001_1")
        ),
    )
    detail = query_gateway.get_case_detail(batch_id, "demo_case_001")
    assert isinstance(detail, CaseDetailView)
    assert detail.batch_id == "detail"
    assert detail.case_id == "demo_case_001"
    assert detail.customer_display_id == "CUST-DEMO-000001"
    assert detail.is_high_value is True
    assert detail.customer_value_summary == (
        "高价值客户：R=88<=397 且 M=2860.42>=209.604，满足高价值判定"
    )
    assert detail.status == "PENDING_REVIEW"
    assert detail.intervention_level == "MUST_INTERVENE"
    assert detail.risk_summary == DEFAULT_RISK_SUMMARY
    assert detail.primary_cause == {"cause_category": "PRODUCT_ISSUE", "confidence": 0.9}
    assert detail.actions == [{"action_type": "CUSTOMER_CONTACT", "content": "联系客户"}]
    assert detail.communication_points == [{"point": "致歉并说明换货进度"}]
    assert detail.uncertainty == ["配送时间不确定"]
    assert detail.missing_evidence == ["order_delivery_detail"]
    assert detail.is_mock is True
    assert detail.can_rerun is True
    assert detail.can_review is True
    assert detail.review_token is not None
    assert detail.review_options is not None
    assert [o.value for o in detail.review_options.intervention_levels] == [
        "MUST_INTERVENE",
        "SHOULD_INTERVENE",
        "NO_IMMEDIATE_INTERVENTION",
    ]
    assert detail.processing_error is None
    assert detail.review_result is None


def test_case_detail_cited_evidence_views(query_gateway, gateway, engine) -> None:
    batch_id = _import_batch(gateway, batch_id="cited", case_ids=("demo_case_001",))
    _complete_current_run(
        engine,
        batch_id=batch_id,
        case_id="demo_case_001",
        run_id="cited-run-1",
        status=CaseStatus.PENDING_REVIEW,
        stages=_standard_stages(
            cited_ids=("ev_text_demo_case_001_1", "ev_behavior_demo_case_001_1")
        ),
    )
    detail = query_gateway.get_case_detail(batch_id, "demo_case_001")
    cited = {evidence.evidence_id: evidence for evidence in (detail.cited_evidence or [])}
    assert set(cited) == {
        "ev_image_demo_case_001",
        "ev_text_demo_case_001_1",
        "ev_behavior_demo_case_001_1",
    }
    image = cited["ev_image_demo_case_001"]
    assert image.modality == "image"
    assert image.label == "售后图片"
    assert image.summary == "商品外观有划痕"
    assert image.text is None
    text = cited["ev_text_demo_case_001_1"]
    assert text.modality == "text"
    assert text.label == "客户对话"
    assert text.text == "收到的商品有划痕，请帮我处理。"
    behavior = cited["ev_behavior_demo_case_001_1"]
    assert behavior.modality == "behavior"
    assert behavior.label == "订单与客户价值事实"
    assert behavior.text == "高价值客户标识：是"


def test_case_detail_separates_current_from_first_history(
    query_gateway, gateway, engine
) -> None:
    batch_id = _import_batch(gateway, batch_id="hist")
    first = _complete_current_run(
        engine,
        batch_id=batch_id,
        case_id="demo_case_001",
        run_id="hist-run-first",
        status=CaseStatus.PENDING_REVIEW,
        system_level=InterventionLevel.SHOULD_INTERVENE,
        stages=_standard_stages(
            risk_summary="首次批量分析风险",
            cited_ids=("ev_text_demo_case_001_1",),
        ),
    )
    _complete_current_run(
        engine,
        batch_id=batch_id,
        case_id="demo_case_001",
        run_id="hist-run-current",
        previous_case_run_id=first,
        status=CaseStatus.PENDING_REVIEW,
        system_level=InterventionLevel.MUST_INTERVENE,
        stages=_standard_stages(risk_summary="重跑后的当前风险"),
    )
    detail = query_gateway.get_case_detail(batch_id, "demo_case_001")
    # 详情只投影当前 case_run：风险摘要取当前运行
    assert detail.risk_summary == "重跑后的当前风险"
    assert detail.intervention_level == "MUST_INTERVENE"
    # 首次历史引用的文本证据不进入当前投影
    cited_ids = [evidence.evidence_id for evidence in (detail.cited_evidence or [])]
    assert "ev_image_demo_case_001" in cited_ids
    assert "ev_text_demo_case_001_1" not in cited_ids
    assert detail.status == "PENDING_REVIEW"
    assert detail.review_token is not None


def test_case_detail_review_token_changes_on_rerun(query_gateway, gateway, engine) -> None:
    batch_id = _import_batch(gateway, batch_id="tok")
    first = _complete_current_run(
        engine,
        batch_id=batch_id,
        case_id="demo_case_001",
        run_id="tok-run-1",
        status=CaseStatus.PENDING_REVIEW,
        stages=_standard_stages(),
    )
    detail1 = query_gateway.get_case_detail(batch_id, "demo_case_001")
    expected1 = hashlib.sha256(
        f"psit-review:{batch_id}:demo_case_001:tok-run-1".encode()
    ).hexdigest()
    assert detail1.can_review is True
    assert detail1.review_token == expected1

    _complete_current_run(
        engine,
        batch_id=batch_id,
        case_id="demo_case_001",
        run_id="tok-run-2",
        previous_case_run_id=first,
        status=CaseStatus.PENDING_REVIEW,
        stages=_standard_stages(),
    )
    detail2 = query_gateway.get_case_detail(batch_id, "demo_case_001")
    expected2 = hashlib.sha256(
        f"psit-review:{batch_id}:demo_case_001:tok-run-2".encode()
    ).hexdigest()
    assert detail2.review_token == expected2
    # 结果被重跑替换后旧 Token 失效（规格 12.3）
    assert detail2.review_token != detail1.review_token
    assert detail2.review_token != expected1


def test_case_detail_can_rerun_can_review_matrix(query_gateway, gateway, engine) -> None:
    batch_id = _import_batch(gateway, batch_id="mtx", case_ids=("c1", "c2", "c3", "c4", "c5"))
    _complete_current_run(
        engine,
        batch_id=batch_id,
        case_id="c1",
        run_id="mtx-c1-1",
        status=CaseStatus.PENDING_REVIEW,
        system_level=InterventionLevel.MUST_INTERVENE,
        stages=_standard_stages(case_id="c1"),
    )
    _complete_current_run(
        engine,
        batch_id=batch_id,
        case_id="c2",
        run_id="mtx-c2-1",
        status=CaseStatus.PROCESSING_ERROR,
        run_status=CaseRunStatus.FAILED,
        error_code="MODEL_TIMEOUT",
        error_stage="strategy",
        stages={},
    )
    _complete_current_run(
        engine,
        batch_id=batch_id,
        case_id="c3",
        run_id="mtx-c3-1",
        status=CaseStatus.COMPLETED,
        system_level=InterventionLevel.NO_IMMEDIATE_INTERVENTION,
        stages=_standard_stages(case_id="c3"),
    )
    # c4：PENDING_ANALYSIS，无任何运行
    _complete_current_run(
        engine,
        batch_id=batch_id,
        case_id="c5",
        run_id="mtx-c5-1",
        status=CaseStatus.PENDING_REVIEW,
        system_level=InterventionLevel.SHOULD_INTERVENE,
        stages=_standard_stages(case_id="c5"),
    )
    _insert_active_case_run(engine, batch_id=batch_id, case_id="c5", run_id="mtx-c5-active")

    d1 = query_gateway.get_case_detail(batch_id, "c1")
    assert (d1.can_rerun, d1.can_review) == (True, True)
    d2 = query_gateway.get_case_detail(batch_id, "c2")
    assert (d2.can_rerun, d2.can_review) == (True, False)
    assert d2.processing_error is not None
    d3 = query_gateway.get_case_detail(batch_id, "c3")
    assert (d3.can_rerun, d3.can_review) == (False, False)
    d4 = query_gateway.get_case_detail(batch_id, "c4")
    assert (d4.can_rerun, d4.can_review) == (False, False)
    d5 = query_gateway.get_case_detail(batch_id, "c5")
    assert (d5.can_rerun, d5.can_review) == (False, True)


def test_case_detail_review_result_human_first(query_gateway, gateway, engine) -> None:
    batch_id = _import_batch(gateway, batch_id="rv1")
    run_id = _complete_current_run(
        engine,
        batch_id=batch_id,
        case_id="demo_case_001",
        run_id="rv1-run-1",
        status=CaseStatus.PENDING_REVIEW,
        system_level=InterventionLevel.SHOULD_INTERVENE,
        stages=_standard_stages(intervention_level="SHOULD_INTERVENE"),
    )
    _insert_review(
        engine,
        batch_id=batch_id,
        case_id="demo_case_001",
        case_run_id=run_id,
        outcome=ReviewOutcome.APPROVED,
        final_level=InterventionLevel.MUST_INTERVENE,
        final_cause={"cause_category": "PRICE_OR_BENEFIT"},
        final_actions=[{"action_type": "NO_ACTION_MONITOR"}],
        review_reason="人工复核为价格或权益问题",
        execution_note="已联系客户确认权益补偿方案",
    )
    detail = query_gateway.get_case_detail(batch_id, "demo_case_001")
    assert detail.status == "COMPLETED"
    review_result = detail.review_result
    assert review_result is not None
    assert review_result.outcome == "APPROVED"
    assert review_result.final_intervention_level == "MUST_INTERVENE"
    assert review_result.final_cause == {"cause_category": "PRICE_OR_BENEFIT"}
    assert review_result.final_actions == [{"action_type": "NO_ACTION_MONITOR"}]
    assert review_result.review_reason == "人工复核为价格或权益问题"
    assert review_result.execution_note == "已联系客户确认权益补偿方案"
    assert review_result.created_at.endswith("+00:00")
    assert detail.can_review is False
    assert detail.review_token is None
    assert detail.review_options is None


def test_case_detail_review_result_system_fallback(query_gateway, gateway, engine) -> None:
    batch_id = _import_batch(gateway, batch_id="rv2")
    run_id = _complete_current_run(
        engine,
        batch_id=batch_id,
        case_id="demo_case_001",
        run_id="rv2-run-1",
        status=CaseStatus.PENDING_REVIEW,
        stages=_standard_stages(intervention_level="SHOULD_INTERVENE"),
    )
    # 人工未填 final 字段时，回退到系统 attribution/strategy 结果
    _insert_review(
        engine,
        batch_id=batch_id,
        case_id="demo_case_001",
        case_run_id=run_id,
        outcome=ReviewOutcome.APPROVED,
    )
    detail = query_gateway.get_case_detail(batch_id, "demo_case_001")
    review_result = detail.review_result
    assert review_result is not None
    assert review_result.final_intervention_level == "SHOULD_INTERVENE"
    assert review_result.final_cause == {"cause_category": "PRODUCT_ISSUE", "confidence": 0.9}
    assert review_result.final_actions == [
        {"action_type": "CUSTOMER_CONTACT", "content": "联系客户"}
    ]


@pytest.mark.parametrize(
    ("error_stage", "expected_stage"),
    [
        ("input_preparation", "INPUT_PREPARATION"),
        ("perception", "EVIDENCE_PROCESSING"),
        ("image", "EVIDENCE_PROCESSING"),
        ("evidence", "EVIDENCE_PROCESSING"),
        ("attribution", "AI_ANALYSIS"),
        ("strategy", "AI_ANALYSIS"),
        ("result_persistence", "RESULT_PERSISTENCE"),
        ("app_recovery", "APP_RECOVERY"),
        ("unknown_stage", "AI_ANALYSIS"),
    ],
)
def test_processing_error_stage_mapping(
    query_gateway, gateway, engine, error_stage: str, expected_stage: str
) -> None:
    batch_id = _import_batch(gateway, batch_id="perr")
    _complete_current_run(
        engine,
        batch_id=batch_id,
        case_id="demo_case_001",
        run_id=f"perr-{error_stage}",
        status=CaseStatus.PROCESSING_ERROR,
        run_status=CaseRunStatus.FAILED,
        error_code="MODEL_TIMEOUT",
        error_stage=error_stage,
        error_detail_json={"trace_id": "tr-1"},
        stages={},
    )
    detail = query_gateway.get_case_detail(batch_id, "demo_case_001")
    assert detail.processing_error is not None
    assert detail.processing_error.stage == expected_stage
    assert detail.processing_error.code == "MODEL_TIMEOUT"
    assert detail.processing_error.message == "模型调用超时"
    assert detail.processing_error.next_action == "稍后重试或人工核验"
    assert detail.processing_error.trace_id == "tr-1"


def test_processing_error_unknown_code_fallback(query_gateway, gateway, engine) -> None:
    batch_id = _import_batch(gateway, batch_id="perr2")
    _complete_current_run(
        engine,
        batch_id=batch_id,
        case_id="demo_case_001",
        run_id="perr2-run-1",
        status=CaseStatus.PROCESSING_ERROR,
        run_status=CaseRunStatus.FAILED,
        error_code="BRAND_NEW_ERROR",
        error_stage="future_stage",
        stages={},
    )
    detail = query_gateway.get_case_detail(batch_id, "demo_case_001")
    assert detail.processing_error is not None
    assert detail.processing_error.code == "BRAND_NEW_ERROR"
    assert detail.processing_error.message == "处理过程发生异常"
    assert detail.processing_error.stage == "AI_ANALYSIS"


def test_processing_error_empty_code_defaults(query_gateway, gateway, engine) -> None:
    batch_id = _import_batch(gateway, batch_id="perr3")
    _complete_current_run(
        engine,
        batch_id=batch_id,
        case_id="demo_case_001",
        run_id="perr3-run-1",
        status=CaseStatus.PROCESSING_ERROR,
        run_status=CaseRunStatus.FAILED,
        error_code=None,
        error_stage=None,
        stages={},
    )
    detail = query_gateway.get_case_detail(batch_id, "demo_case_001")
    assert detail.processing_error is not None
    assert detail.processing_error.code == "UNEXPECTED_PROCESSING_ERROR"
    assert detail.processing_error.message == "处理过程发生未预期错误"
    assert detail.processing_error.stage == "AI_ANALYSIS"


# ---------- CaseInput 查询与视图合同 ----------

def test_get_case_input_roundtrip_and_missing(query_gateway, gateway) -> None:
    batch_id = _import_batch(gateway, batch_id="input1")
    case_input = query_gateway.get_case_input(batch_id, "demo_case_001")
    assert case_input is not None
    assert case_input.case_id == "demo_case_001"
    assert case_input.data_identity == "simulated"
    assert case_input.customer.customer_ref == "CUST-DEMO-000001"
    assert query_gateway.get_case_input("no-such-batch", "demo_case_001") is None
    assert query_gateway.get_case_input(batch_id, "no-such-case") is None


def test_review_options_catalog_of_record() -> None:
    options = build_review_options()
    assert options.action_catalog_version == "action_catalog.v1"
    assert [o.value for o in options.intervention_levels] == [
        "MUST_INTERVENE",
        "SHOULD_INTERVENE",
        "NO_IMMEDIATE_INTERVENTION",
    ]
    assert len(options.cause_categories) == 6
    action_values = [o.value for o in options.action_types]
    assert len(action_values) == 6
    assert "INSUFFICIENT_EVIDENCE" not in action_values


def test_dtos_reject_extra_and_loose_types() -> None:
    payload = {
        "case_id": "demo_case_001",
        "customer_display_id": "CUST-DEMO-000001",
        "is_high_value": True,
        "status": "PENDING_ANALYSIS",
        "has_evidence_conflict": False,
        "has_insufficient_evidence": False,
        "has_modality_failure": False,
    }
    with pytest.raises(ValidationError):
        CaseQueueItemView.model_validate({**payload, "unexpected_field": 1})
    with pytest.raises(ValidationError):
        CaseQueueItemView.model_validate({**payload, "case_id": 123})
