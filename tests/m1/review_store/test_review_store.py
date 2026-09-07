"""M1-08：ReviewStore 正式人工确认命令测试（规格 8/10.3/11.1/12.3/12.4）。

自动验收覆盖：
- 四种 outcome 合法提交：APPROVED / MODIFIED_AND_APPROVED /
  REJECTED_WITH_JUDGMENT / INSUFFICIENT_EVIDENCE 按 12.3 表格落库；视图
  final_* 落库值优先、系统原结果经 stage_results 回填，案例/批次投影与计数
  同步；
- 字段规则负向：缺必填、final_cause/final_actions 额外键、非法 outcome、
  APPROVED 带 final_*、INSUFFICIENT_EVIDENCE 缺 review_reason →
  REQUEST_VALIDATION_FAILED，整体回滚无半写入；
- 幂等：同一 submission_id 重复提交返回同一结果，不新增行；
- 过期运行：重跑切换当前运行后，旧运行+旧 token → STALE_CASE_RESULT，
  新运行新 token → CASE_ALREADY_COMPLETED；
- 并发兜底：预插 review 行模拟唯一约束冲突 → CASE_ALREADY_COMPLETED /
  同 submission_id 幂等返回（真网关 IntegrityError 分支）。

测试先经 BatchImportGateway 导入真实案例基线，RunStore 发布完整决策包构造
PENDING_REVIEW 案例，再走 ReviewStore.submit_review 全链路；只读断言直接查
迁移出的真实 SQLite 行（不 mock Session）。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from zip_fixtures import make_case, make_entries, make_zip

from app.contracts.states import BatchRunStatus, BatchStatus, CaseStatus, TriggerType
from app.modules.data.db.models import (
    Batch,
    Case,
    InterventionLevel,
    Review,
    ReviewOutcome,
)
from app.modules.data.review_store import (
    CaseAlreadyCompletedError,
    ReviewFieldValidationError,
    ReviewStore,
    ReviewStoreResourceNotFoundError,
    ReviewSubmitInput,
    StaleCaseResultError,
)
from app.modules.data.run_store import (
    COMPLETE_PACKAGE_STAGES,
    RunStore,
    StageResultInput,
)

OCCURRED_AT = datetime(2026, 9, 1, 6, 0, 0, tzinfo=UTC)
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


def _batch_row(session: Session, *, batch_id: str) -> Batch:
    batch = session.scalar(select(Batch).where(Batch.batch_id == batch_id))
    assert batch is not None, batch_id
    return batch


def _case_row(session: Session, *, batch_id: str, case_id: str) -> Case:
    batch = _batch_row(session, batch_id=batch_id)
    case = session.scalar(
        select(Case).where(Case.batch_id == batch.id, Case.case_id == case_id)
    )
    assert case is not None, f"{batch_id}/{case_id}"
    return case


def _standard_stages(*, case_id: str = "demo_case_001") -> dict[str, dict[str, Any]]:
    """生成 perception/attribution/strategy 三个标准阶段结果（约定键）。"""
    return {
        "perception": {
            "risk_summary": DEFAULT_RISK_SUMMARY,
            "image_observations": [
                {
                    "evidence_id": f"ev_image_{case_id}",
                    "observable_facts": ["商品外观有划痕"],
                }
            ],
        },
        "attribution": {
            "primary_cause": {"cause_category": "PRODUCT_ISSUE", "confidence": 0.9},
            "support_evidence": [],
            "has_evidence_conflict": False,
        },
        "strategy": {
            "intervention_level": "MUST_INTERVENE",
            "priority_reason": DEFAULT_PRIORITY_REASON,
            "actions": [{"action_type": "CUSTOMER_CONTACT", "content": "联系客户"}],
            "communication_points": [{"point": "致歉并说明换货进度"}],
            "execution_note": "已生成沟通要点",
            "has_insufficient_evidence": False,
            "has_modality_failure": False,
            "uncertainty": ["配送时间不确定"],
            "missing_evidence": ["order_delivery_detail"],
        },
    }


def _stage_input(
    stage_name: str,
    *,
    case_id: str = "demo_case_001",
    result_json: dict[str, Any] | None = None,
) -> StageResultInput:
    """构造一份标准阶段结果输入；sha256 与实际 JSON 内容自洽。"""
    payload = _standard_stages(case_id=case_id).get(stage_name)
    if payload is None:
        raise AssertionError(f"未知阶段: {stage_name}")
    content = result_json if result_json is not None else payload
    sha256 = hashlib.sha256(
        json.dumps(content, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return StageResultInput(
        stage_name=stage_name,
        contract_version="decision_package.v1",
        result_json=content,
        result_sha256=sha256,
    )


def _review_token(batch_id: str, case_id: str, run_id: str) -> str:
    """按规格 12.3 文档算法生成 review_token（与 M1-05/ReviewStore 同源）。"""
    digest = hashlib.sha256(f"psit-review:{batch_id}:{case_id}:{run_id}".encode())
    return digest.hexdigest()


def _publish_review_ready(
    run_store: RunStore,
    *,
    batch_id: str,
    case_id: str,
    run_id: str,
    batch_run_id: str | None,
) -> tuple[int, str]:
    """创建案例运行、记录完整决策包并原子发布，返回 (case_run_id, run_id)。"""
    case_run = run_store.create_case_run(
        batch_id=batch_id,
        case_id=case_id,
        run_id=run_id,
        trigger_type=TriggerType.BATCH if batch_run_id else TriggerType.MANUAL_RERUN,
        batch_run_id=batch_run_id,
    )
    for stage_name in COMPLETE_PACKAGE_STAGES:
        run_store.record_stage_result(
            case_run_id=case_run.id, stage=_stage_input(stage_name, case_id=case_id)
        )
    run_store.publish_complete_result(
        case_run_id=case_run.id,
        final_stage=_stage_input("strategy", case_id=case_id),
        system_intervention_level="MUST_INTERVENE",
    )
    return case_run.id, case_run.run_id


def _ready_case(
    *,
    gateway,
    run_store: RunStore,
    batch_id: str,
    case_id: str = "demo_case_001",
) -> tuple[int, str]:
    """导入单案例批次、创建首次批次运行并发布完整决策包，返回 (case_run_id, token)。"""
    _import_batch(gateway, batch_id=batch_id, case_ids=(case_id,))
    batch_view = run_store.create_batch_run(
        batch_id=batch_id, run_id=f"{batch_id}-batch-1", total_case_count=1
    )
    case_run_id, run_id = _publish_review_ready(
        run_store,
        batch_id=batch_id,
        case_id=case_id,
        run_id=f"{batch_id}-cr-1",
        batch_run_id=batch_view.run_id,
    )
    return case_run_id, _review_token(batch_id, case_id, run_id)


def _approved_payload() -> ReviewSubmitInput:
    return ReviewSubmitInput(outcome="APPROVED")


def _modified_payload() -> ReviewSubmitInput:
    return ReviewSubmitInput(
        outcome="MODIFIED_AND_APPROVED",
        final_intervention_level="SHOULD_INTERVENE",
        final_cause={"cause_category": "LOGISTICS_FULFILLMENT"},
        final_actions=[{"action_type": "FULFILLMENT_ESCALATION"}],
        review_reason="物流时效问题，需升级履约处理",
        execution_note="已与客户确认补发时间",
    )


def _rejected_payload() -> ReviewSubmitInput:
    return ReviewSubmitInput(
        outcome="REJECTED_WITH_JUDGMENT",
        final_intervention_level="MUST_INTERVENE",
        final_cause={"cause_category": "PRODUCT_ISSUE"},
        final_actions=[
            {"action_type": "CUSTOMER_CONTACT"},
            {"action_type": "REPLACEMENT_RETURN_REFUND_CHECK"},
        ],
        review_reason="商品问题明确，建议换货并联系客户",
    )


def _insufficient_payload() -> ReviewSubmitInput:
    return ReviewSubmitInput(
        outcome="INSUFFICIENT_EVIDENCE",
        review_reason="图片与订单信息不足以判定责任归属",
    )


# ---------- 1. 四种 outcome 合法提交与投影 ----------

def test_four_outcomes_submit_persist_and_project(
    review_store: ReviewStore, run_store: RunStore, gateway, engine: Engine
) -> None:
    scenarios = (
        ("rv1", "approve-001", _approved_payload(), "APPROVED"),
        ("rv2", "modify-001", _modified_payload(), "MODIFIED_AND_APPROVED"),
        ("rv3", "reject-001", _rejected_payload(), "REJECTED_WITH_JUDGMENT"),
        ("rv4", "insuff-001", _insufficient_payload(), "INSUFFICIENT_EVIDENCE"),
    )
    for batch_id, submission_id, payload, expected in scenarios:
        case_run_id, token = _ready_case(
            gateway=gateway, run_store=run_store, batch_id=batch_id
        )
        view = review_store.submit_review(
            submission_id=submission_id,
            case_run_id=case_run_id,
            review_token=token,
            payload=payload,
            occurred_at=OCCURRED_AT,
        )
        assert view.outcome == expected
        assert view.created_at == OCCURRED_AT.isoformat()
        assert view.execution_note == "已生成沟通要点"  # 系统原结果（strategy）回填
        if expected == "APPROVED":
            assert view.final_intervention_level == "MUST_INTERVENE"
            assert view.final_cause == {
                "cause_category": "PRODUCT_ISSUE",
                "confidence": 0.9,
            }
            assert view.final_actions == [
                {"action_type": "CUSTOMER_CONTACT", "content": "联系客户"}
            ]
            assert view.review_reason is None
            final_level = None
            review_reason = None
        elif expected == "MODIFIED_AND_APPROVED":
            assert view.final_intervention_level == "SHOULD_INTERVENE"
            assert view.final_cause == {"cause_category": "LOGISTICS_FULFILLMENT"}
            assert view.final_actions == [{"action_type": "FULFILLMENT_ESCALATION"}]
            assert view.review_reason == "物流时效问题，需升级履约处理"
            final_level = InterventionLevel.SHOULD_INTERVENE
            review_reason = "物流时效问题，需升级履约处理"
        elif expected == "REJECTED_WITH_JUDGMENT":
            assert view.final_intervention_level == "MUST_INTERVENE"
            assert view.final_cause == {"cause_category": "PRODUCT_ISSUE"}
            assert view.final_actions == [
                {"action_type": "CUSTOMER_CONTACT"},
                {"action_type": "REPLACEMENT_RETURN_REFUND_CHECK"},
            ]
            assert view.review_reason == "商品问题明确，建议换货并联系客户"
            final_level = InterventionLevel.MUST_INTERVENE
            review_reason = "商品问题明确，建议换货并联系客户"
        else:  # INSUFFICIENT_EVIDENCE
            assert view.final_intervention_level == "MUST_INTERVENE"
            assert view.final_cause == {
                "cause_category": "PRODUCT_ISSUE",
                "confidence": 0.9,
            }
            assert view.final_actions == [
                {"action_type": "CUSTOMER_CONTACT", "content": "联系客户"}
            ]
            assert view.review_reason == "图片与订单信息不足以判定责任归属"
            final_level = None
            review_reason = "图片与订单信息不足以判定责任归属"

        with Session(engine) as session:
            review = session.scalar(
                select(Review).where(Review.submission_id == submission_id)
            )
            assert review is not None
            assert review.review_id == f"review-{submission_id}"
            assert review.case_run_id == case_run_id
            assert review.outcome == ReviewOutcome(expected)
            assert review.final_intervention_level == final_level
            assert review.review_reason == review_reason
            assert review.created_at.replace(tzinfo=UTC) == OCCURRED_AT
            case = _case_row(session, batch_id=batch_id, case_id="demo_case_001")
            assert case.status == CaseStatus.COMPLETED
            assert case.current_review_id == review.id
            assert case.system_intervention_level == InterventionLevel.MUST_INTERVENE
            assert case.final_intervention_level == final_level
            batch = _batch_row(session, batch_id=batch_id)
            assert batch.status == BatchStatus.COMPLETED
            assert batch.analysis_succeeded_count == 1
            assert batch.error_count == 0
        # 模拟 M3 判定首次分析结束：关闭本次批次运行后再构造下一批次
        # （RunStore 同一时刻全系统仅允许一个活动批次运行，规格 10.1/10.3）。
        runs = run_store.batch_run_history(batch_id=batch_id)
        assert len(runs) == 1
        run_store.finish_batch_run(
            batch_run_id=runs[0].id, status=BatchRunStatus.COMPLETED
        )


# ---------- 2. 字段规则负向与整体回滚 ----------

@pytest.mark.parametrize(
    ("payload", "message_fragment"),
    [
        (ReviewSubmitInput(outcome="MODIFIED_AND_APPROVED"), "final_intervention_level"),
        (
            ReviewSubmitInput(
                outcome="REJECTED_WITH_JUDGMENT",
                final_intervention_level="MUST_INTERVENE",
                final_cause={"cause_category": "PRODUCT_ISSUE", "confidence": 0.9},
                final_actions=[{"action_type": "CUSTOMER_CONTACT"}],
                review_reason="原因",
            ),
            "final_cause",
        ),
        (
            ReviewSubmitInput(
                outcome="MODIFIED_AND_APPROVED",
                final_intervention_level="MUST_INTERVENE",
                final_cause={"cause_category": "PRODUCT_ISSUE"},
                final_actions=[
                    {"action_type": "CUSTOMER_CONTACT", "content": "联系客户"}
                ],
                review_reason="原因",
            ),
            "final_actions",
        ),
        (
            ReviewSubmitInput(
                outcome="APPROVED",
                final_intervention_level="MUST_INTERVENE",
            ),
            "禁止提供 final_intervention_level",
        ),
        (ReviewSubmitInput(outcome="INSUFFICIENT_EVIDENCE"), "review_reason"),
        (ReviewSubmitInput(outcome="UNKNOWN_OUTCOME"), "outcome"),
    ],
    ids=[
        "modified_missing_level",
        "cause_extra_key",
        "action_extra_key",
        "approved_forbids_final",
        "insufficient_missing_reason",
        "unknown_outcome",
    ],
)
def test_invalid_field_payload_rejected_and_rolled_back(
    review_store: ReviewStore,
    run_store: RunStore,
    gateway,
    engine: Engine,
    payload: ReviewSubmitInput,
    message_fragment: str,
) -> None:
    batch_id = "inv"
    case_run_id, token = _ready_case(
        gateway=gateway, run_store=run_store, batch_id=batch_id
    )
    with Session(engine) as session:
        batch_status_before = _batch_row(session, batch_id=batch_id).status
    with pytest.raises(ReviewFieldValidationError) as err:
        review_store.submit_review(
            submission_id="inv-sub",
            case_run_id=case_run_id,
            review_token=token,
            payload=payload,
        )
    assert err.value.code == "REQUEST_VALIDATION_FAILED"
    assert message_fragment in err.value.message
    with Session(engine) as session:
        assert list(session.scalars(select(Review))) == []
        case = _case_row(session, batch_id=batch_id, case_id="demo_case_001")
        assert case.status == CaseStatus.PENDING_REVIEW
        assert case.current_review_id is None
        batch = _batch_row(session, batch_id=batch_id)
        assert batch.status == batch_status_before


# ---------- 3. 幂等：同一 submission_id ----------

def test_resubmit_same_submission_id_is_idempotent(
    review_store: ReviewStore, run_store: RunStore, gateway, engine: Engine
) -> None:
    batch_id = "idem"
    case_run_id, token = _ready_case(
        gateway=gateway, run_store=run_store, batch_id=batch_id
    )
    first = review_store.submit_review(
        submission_id="idem-sub",
        case_run_id=case_run_id,
        review_token=token,
        payload=_modified_payload(),
        occurred_at=OCCURRED_AT,
    )
    second = review_store.submit_review(
        submission_id="idem-sub",
        case_run_id=case_run_id,
        review_token=token,
        payload=_approved_payload(),
        occurred_at=OCCURRED_AT,
    )
    assert second == first
    assert second.created_at == OCCURRED_AT.isoformat()
    with Session(engine) as session:
        rows = list(session.scalars(select(Review)))
        assert len(rows) == 1
        assert rows[0].submission_id == "idem-sub"


# ---------- 4. 过期运行与已完成案例 ----------

def test_rerun_makes_old_token_stale_and_blocks_new_review(
    review_store: ReviewStore, run_store: RunStore, gateway, engine: Engine
) -> None:
    batch_id = "stale"
    case_run_1, token_1 = _ready_case(
        gateway=gateway, run_store=run_store, batch_id=batch_id
    )
    review_store.submit_review(
        submission_id="stale-sub-1",
        case_run_id=case_run_1,
        review_token=token_1,
        payload=_approved_payload(),
    )
    case_run_2, run_id_2 = _publish_review_ready(
        run_store,
        batch_id=batch_id,
        case_id="demo_case_001",
        run_id="stale-cr-2",
        batch_run_id=None,
    )
    token_2 = _review_token(batch_id, "demo_case_001", run_id_2)
    with pytest.raises(StaleCaseResultError) as err_1:
        review_store.submit_review(
            submission_id="stale-sub-2",
            case_run_id=case_run_1,
            review_token=token_1,
            payload=_approved_payload(),
        )
    assert err_1.value.code == "STALE_CASE_RESULT"
    with pytest.raises(CaseAlreadyCompletedError) as err_2:
        review_store.submit_review(
            submission_id="stale-sub-3",
            case_run_id=case_run_2,
            review_token=token_2,
            payload=_approved_payload(),
        )
    assert err_2.value.code == "CASE_ALREADY_COMPLETED"
    with Session(engine) as session:
        rows = list(session.scalars(select(Review)))
        assert len(rows) == 1
        case = _case_row(session, batch_id=batch_id, case_id="demo_case_001")
        assert case.current_case_run_id == case_run_2
        assert case.current_review_id is not None


def test_wrong_token_rejected_as_stale(
    review_store: ReviewStore, run_store: RunStore, gateway
) -> None:
    batch_id = "tok"
    case_run_id, _token = _ready_case(
        gateway=gateway, run_store=run_store, batch_id=batch_id
    )
    with pytest.raises(StaleCaseResultError) as err:
        review_store.submit_review(
            submission_id="tok-sub",
            case_run_id=case_run_id,
            review_token="invalid-token",
            payload=_approved_payload(),
        )
    assert err.value.code == "STALE_CASE_RESULT"


def test_unknown_case_run_returns_resource_not_found(
    review_store: ReviewStore, run_store: RunStore, gateway
) -> None:
    batch_id = "nf"
    _ready_case(gateway=gateway, run_store=run_store, batch_id=batch_id)
    with pytest.raises(ReviewStoreResourceNotFoundError) as err:
        review_store.submit_review(
            submission_id="nf-sub",
            case_run_id=999_999,
            review_token="irrelevant",
            payload=_approved_payload(),
        )
    assert err.value.code == "RESOURCE_NOT_FOUND"


# ---------- 5. 并发兜底（真实唯一约束 → IntegrityError 分支） ----------

def test_concurrent_race_same_case_yields_already_completed(
    review_store: ReviewStore, run_store: RunStore, gateway, engine: Engine
) -> None:
    batch_id = "race"
    case_run_id, token = _ready_case(
        gateway=gateway, run_store=run_store, batch_id=batch_id
    )
    with Session(engine) as session:
        case = _case_row(session, batch_id=batch_id, case_id="demo_case_001")
        concurrent = Review(
            review_id="review-race-other",
            submission_id="race-other",
            case_id=case.id,
            case_run_id=case_run_id,
            outcome=ReviewOutcome.APPROVED,
            created_at=OCCURRED_AT,
        )
        session.add(concurrent)
        session.commit()
    with pytest.raises(CaseAlreadyCompletedError) as err:
        review_store.submit_review(
            submission_id="race-sub",
            case_run_id=case_run_id,
            review_token=token,
            payload=_approved_payload(),
        )
    assert err.value.code == "CASE_ALREADY_COMPLETED"
    with Session(engine) as session:
        rows = list(session.scalars(select(Review)))
        assert len(rows) == 1


def test_concurrent_race_same_submission_returns_existing(
    review_store: ReviewStore, run_store: RunStore, gateway, engine: Engine
) -> None:
    batch_id = "race2"
    case_run_id, token = _ready_case(
        gateway=gateway, run_store=run_store, batch_id=batch_id
    )
    with Session(engine) as session:
        case = _case_row(session, batch_id=batch_id, case_id="demo_case_001")
        existing = Review(
            review_id="review-race2-sub",
            submission_id="race2-sub",
            case_id=case.id,
            case_run_id=case_run_id,
            outcome=ReviewOutcome.MODIFIED_AND_APPROVED,
            final_intervention_level=InterventionLevel.SHOULD_INTERVENE,
            final_cause_json={"cause_category": "LOGISTICS_FULFILLMENT"},
            final_actions_json=[{"action_type": "FULFILLMENT_ESCALATION"}],
            review_reason="物流时效问题，需升级履约处理",
            created_at=OCCURRED_AT,
        )
        session.add(existing)
        session.flush()
        case.current_review_id = existing.id
        session.commit()
    view = review_store.submit_review(
        submission_id="race2-sub",
        case_run_id=case_run_id,
        review_token=token,
        payload=_approved_payload(),
        occurred_at=OCCURRED_AT,
    )
    assert view.outcome == "MODIFIED_AND_APPROVED"
    assert view.created_at == OCCURRED_AT.isoformat()
    assert view.final_intervention_level == "SHOULD_INTERVENE"
    with Session(engine) as session:
        rows = list(session.scalars(select(Review)))
        assert len(rows) == 1
