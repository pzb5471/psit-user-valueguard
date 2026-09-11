"""M1-07：RunStore 运行历史、事件追加与原子发布测试（规格 8/9.1/9.2/10.1—10.5/11.1/11.2）。

自动验收覆盖：
- 阶段事件追加：STAGE_STARTED / MODEL_ATTEMPT_FINISHED / STAGE_RESULT_VALIDATED
  落库，call_id 幂等、case_run.current_stage 前进；
- 活动唯一与幂等创建：全系统最多一个活动 batch_run、同一案例最多一个活动
  case_run（数据库部分唯一索引兜底 → ACTIVE_RUN_CONFLICT）；同 run_id 重复
  创建幂等返回；
- 写入回滚：完整决策包缺阶段整体回滚（不发布半个决策包）、阶段结果内容冲突
  回滚，数据库无半写入；
- 成功发布：PENDING_REVIEW + 批次 COMPLETED 投影与三项计数、首次批量运行计数、
  发布幂等重入不重复计数；
- 技术失败：PROCESSING_ERROR + 错误字段落库 + 批次投影/计数；
- 中断恢复：recover_interrupted 把活动运行标 INTERRUPTED、未发布案例进
  PROCESSING_ERROR(APP_INTERRUPTED/app_recovery)、保留诊断 current_stage、
  历史保留、幂等；
- 计数与历史不变性：batch_runs 只保存首次批量统计、MANUAL_RERUN 不创建伪批次
  运行也不改已结束 batch_runs、旧运行与旧阶段结果只追加不覆盖。

测试经 BatchImportGateway 导入真实案例基线后走 RunStore 命令全链路；只读断言
直接查迁移出的真实 SQLite 行（不 mock Session）。与 M1-05 的"实时推导"过渡期
假设一致：批次当前投影在每次 RunStore 命令后同事务重算。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import select
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
    ModelCall,
    StageResult,
)
from app.modules.data.run_store import (
    APP_INTERRUPTED_CODE,
    APP_RECOVERY_STAGE,
    COMPLETE_PACKAGE_STAGES,
    ActiveRunConflictError,
    IncompleteDecisionPackageError,
    ModelAttemptInput,
    RunStore,
    StageResultConflictError,
    StageResultInput,
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
    case_ids: tuple[str, ...] = ("mvp_case_001", "mvp_case_002"),
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


def _standard_stages(*, case_id: str = "mvp_case_001") -> dict[str, dict[str, Any]]:
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
    case_id: str = "mvp_case_001",
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


def _model_attempt(
    *, call_id: str, stage_name: str = "perception"
) -> ModelAttemptInput:
    """构造一次标准模型调用尝试（M1-07 只追加不覆盖，call_id 全局唯一）。"""
    return ModelAttemptInput(
        call_id=call_id,
        stage_name=stage_name,
        attempt_no=1,
        model_name="glm-4.5",
        prompt_version="prompt.v1",
        request_manifest_json={"items": [f"ev_image_{stage_name}"]},
        status="SUCCESS",
        response_json={"risk": "high"},
        latency_ms=120,
        prompt_token_count=10,
        completion_token_count=5,
        total_token_count=15,
    )


# ---------- 1. 阶段事件追加与幂等 ----------

def test_record_stage_events_persist_and_idempotent(
    run_store: RunStore, gateway, engine: Engine
) -> None:
    batch_id = _import_batch(gateway, batch_id="evt")
    batch_view = run_store.create_batch_run(
        batch_id=batch_id, run_id="evt-batch-1", total_case_count=2
    )
    case_run = run_store.create_case_run(
        batch_id=batch_id,
        case_id="mvp_case_001",
        run_id="evt-cr-1",
        trigger_type=TriggerType.BATCH,
        batch_run_id=batch_view.run_id,
    )
    run_store.record_stage_started(
        case_run_id=case_run.id,
        stage_name="perception",
        status=CaseRunStatus.PERCEPTION_RUNNING,
    )
    attempt = _model_attempt(call_id="evt-call-1")
    run_store.record_model_attempt(case_run_id=case_run.id, attempt=attempt)
    run_store.record_model_attempt(case_run_id=case_run.id, attempt=attempt)
    stage = _stage_input("perception")
    run_store.record_stage_result(case_run_id=case_run.id, stage=stage)
    run_store.record_stage_result(case_run_id=case_run.id, stage=stage)

    with Session(engine) as session:
        run_row = session.get(CaseRun, case_run.id)
        assert run_row is not None
        assert run_row.current_stage == "perception"
        assert run_row.status == CaseRunStatus.PERCEPTION_RUNNING
        calls = list(
            session.scalars(
                select(ModelCall).where(ModelCall.case_run_id == case_run.id)
            )
        )
        assert [c.call_id for c in calls] == ["evt-call-1"]
        assert calls[0].stage_name == "perception"
        assert calls[0].total_token_count == 15
        results = list(
            session.scalars(
                select(StageResult).where(StageResult.case_run_id == case_run.id)
            )
        )
        assert [r.stage_name for r in results] == ["perception"]
        assert results[0].result_sha256 == stage.result_sha256


# ---------- 2. 活动唯一与幂等创建 ----------

def test_active_run_uniqueness_and_idempotent_create(
    run_store: RunStore, gateway, engine: Engine
) -> None:
    batch_id = _import_batch(gateway, batch_id="uniq")
    first = run_store.create_batch_run(
        batch_id=batch_id, run_id="uniq-batch-1", total_case_count=2
    )
    second = run_store.create_batch_run(
        batch_id=batch_id, run_id="uniq-batch-1", total_case_count=2
    )
    assert second.id == first.id
    with pytest.raises(ActiveRunConflictError) as err:
        run_store.create_batch_run(
            batch_id=batch_id, run_id="uniq-batch-2", total_case_count=2
        )
    assert err.value.code == "ACTIVE_RUN_CONFLICT"
    assert err.value.object_type == "batch"

    case_run = run_store.create_case_run(
        batch_id=batch_id,
        case_id="mvp_case_001",
        run_id="uniq-cr-1",
        trigger_type=TriggerType.BATCH,
        batch_run_id="uniq-batch-1",
    )
    again = run_store.create_case_run(
        batch_id=batch_id,
        case_id="mvp_case_001",
        run_id="uniq-cr-1",
        trigger_type=TriggerType.BATCH,
        batch_run_id="uniq-batch-1",
    )
    assert again.id == case_run.id
    with pytest.raises(ActiveRunConflictError) as err:
        run_store.create_case_run(
            batch_id=batch_id,
            case_id="mvp_case_001",
            run_id="uniq-cr-2",
            trigger_type=TriggerType.BATCH,
            batch_run_id="uniq-batch-1",
        )
    assert err.value.code == "ACTIVE_RUN_CONFLICT"
    assert err.value.object_type == "case"
    with Session(engine) as session:
        case = _case_row(session, batch_id=batch_id, case_id="mvp_case_001")
        rows = list(
            session.scalars(select(CaseRun).where(CaseRun.case_id == case.id))
        )
        assert [r.run_id for r in rows] == ["uniq-cr-1"]


# ---------- 3. 写入回滚（无半写入） ----------

def test_publish_incomplete_package_rolls_back(
    run_store: RunStore, gateway, engine: Engine
) -> None:
    batch_id = _import_batch(gateway, batch_id="rb1", case_ids=("mvp_case_001",))
    batch_view = run_store.create_batch_run(
        batch_id=batch_id, run_id="rb1-batch-1", total_case_count=1
    )
    case_run = run_store.create_case_run(
        batch_id=batch_id,
        case_id="mvp_case_001",
        run_id="rb1-cr-1",
        trigger_type=TriggerType.BATCH,
        batch_run_id=batch_view.run_id,
    )
    run_store.record_stage_result(
        case_run_id=case_run.id, stage=_stage_input("perception")
    )
    with pytest.raises(IncompleteDecisionPackageError) as err:
        run_store.publish_complete_result(
            case_run_id=case_run.id, final_stage=_stage_input("strategy")
        )
    assert "attribution" in err.value.message

    with Session(engine) as session:
        run_row = session.get(CaseRun, case_run.id)
        assert run_row is not None
        assert run_row.status == CaseRunStatus.STARTING
        assert run_row.finished_at is None
        case = _case_row(session, batch_id=batch_id, case_id="mvp_case_001")
        assert case.status == CaseStatus.ANALYZING
        assert case.current_case_run_id == case_run.id
        results = list(
            session.scalars(
                select(StageResult).where(StageResult.case_run_id == case_run.id)
            )
        )
        assert {r.stage_name for r in results} == {"perception"}
        batch_run = session.scalar(
            select(BatchRun).where(BatchRun.run_id == "rb1-batch-1")
        )
        assert batch_run is not None
        assert batch_run.analysis_succeeded_count == 0
        assert batch_run.error_count == 0


def test_stage_result_conflict_rolls_back(
    run_store: RunStore, gateway, engine: Engine
) -> None:
    batch_id = _import_batch(gateway, batch_id="rb2", case_ids=("mvp_case_001",))
    batch_view = run_store.create_batch_run(
        batch_id=batch_id, run_id="rb2-batch-1", total_case_count=1
    )
    case_run = run_store.create_case_run(
        batch_id=batch_id,
        case_id="mvp_case_001",
        run_id="rb2-cr-1",
        trigger_type=TriggerType.BATCH,
        batch_run_id=batch_view.run_id,
    )
    for stage_name in COMPLETE_PACKAGE_STAGES:
        run_store.record_stage_result(
            case_run_id=case_run.id, stage=_stage_input(stage_name)
        )
    with pytest.raises(StageResultConflictError) as err:
        run_store.publish_complete_result(
            case_run_id=case_run.id,
            final_stage=_stage_input("strategy", result_json={"different": True}),
        )
    assert err.value.code == "STAGE_RESULT_CONFLICT"

    with Session(engine) as session:
        run_row = session.get(CaseRun, case_run.id)
        assert run_row is not None
        assert run_row.status == CaseRunStatus.STARTING
        assert run_row.finished_at is None
        case = _case_row(session, batch_id=batch_id, case_id="mvp_case_001")
        assert case.status == CaseStatus.ANALYZING
        results = list(
            session.scalars(
                select(StageResult).where(StageResult.case_run_id == case_run.id)
            )
        )
        assert {r.stage_name for r in results} == set(COMPLETE_PACKAGE_STAGES)
        assert len(results) == 3  # 无新增、无覆盖


# ---------- 4. 成功原子发布 ----------

def test_publish_complete_result_atomic(
    run_store: RunStore, gateway, engine: Engine
) -> None:
    batch_id = _import_batch(gateway, batch_id="pub")
    batch_view = run_store.create_batch_run(
        batch_id=batch_id, run_id="pub-batch-1", total_case_count=2
    )
    runs = []
    for case_id in ("mvp_case_001", "mvp_case_002"):
        case_run = run_store.create_case_run(
            batch_id=batch_id,
            case_id=case_id,
            run_id=f"pub-cr-{case_id}",
            trigger_type=TriggerType.BATCH,
            batch_run_id=batch_view.run_id,
        )
        runs.append(case_run)
    for case_run in runs:
        for stage_name in ("perception", "attribution"):
            run_store.record_stage_result(
                case_run_id=case_run.id,
                stage=_stage_input(stage_name, case_id=case_run.case_id),
            )
    result = run_store.publish_complete_result(
        case_run_id=runs[0].id,
        final_stage=_stage_input("strategy", case_id="mvp_case_001"),
        system_intervention_level="MUST_INTERVENE",
    )
    assert result.batch_status == BatchStatus.ANALYZING  # 案例二仍 ANALYZING
    assert result.analysis_succeeded_count == 1

    result = run_store.publish_complete_result(
        case_run_id=runs[1].id,
        final_stage=_stage_input("strategy", case_id="mvp_case_002"),
        system_intervention_level="SHOULD_INTERVENE",
    )
    assert result.batch_status == BatchStatus.COMPLETED
    assert result.analysis_succeeded_count == 2
    assert result.error_count == 0
    again = run_store.publish_complete_result(
        case_run_id=runs[1].id,
        final_stage=_stage_input("strategy", case_id="mvp_case_002"),
        system_intervention_level="SHOULD_INTERVENE",
    )
    assert again.analysis_succeeded_count == 2  # 幂等重入不重复计数

    with Session(engine) as session:
        for case_run in runs:
            run_row = session.get(CaseRun, case_run.id)
            assert run_row is not None
            assert run_row.status == CaseRunStatus.SUCCEEDED
            assert run_row.finished_at is not None
            assert run_row.current_stage is None
            case = _case_row(session, batch_id=batch_id, case_id=case_run.case_id)
            assert case.status == CaseStatus.PENDING_REVIEW
            assert case.current_case_run_id == case_run.id
        case1 = _case_row(session, batch_id=batch_id, case_id="mvp_case_001")
        assert case1.system_intervention_level == InterventionLevel.MUST_INTERVENE
        case2 = _case_row(session, batch_id=batch_id, case_id="mvp_case_002")
        assert case2.system_intervention_level == InterventionLevel.SHOULD_INTERVENE
        batch = _batch_row(session, batch_id=batch_id)
        assert batch.status == BatchStatus.COMPLETED
        assert batch.analysis_succeeded_count == 2
        assert batch.error_count == 0
        batch_run = session.scalar(
            select(BatchRun).where(BatchRun.run_id == "pub-batch-1")
        )
        assert batch_run is not None
        assert batch_run.analysis_succeeded_count == 2
        assert batch_run.status == BatchRunStatus.STARTING


# ---------- 5. 技术失败记录 ----------

def test_record_failure_updates_projection_and_counts(
    run_store: RunStore, gateway, engine: Engine
) -> None:
    batch_id = _import_batch(gateway, batch_id="fail", case_ids=("mvp_case_001",))
    batch_view = run_store.create_batch_run(
        batch_id=batch_id, run_id="fail-batch-1", total_case_count=1
    )
    case_run = run_store.create_case_run(
        batch_id=batch_id,
        case_id="mvp_case_001",
        run_id="fail-cr-1",
        trigger_type=TriggerType.BATCH,
        batch_run_id=batch_view.run_id,
    )
    failure = run_store.record_failure(
        case_run_id=case_run.id,
        error_code="MODEL_TIMEOUT",
        error_stage="attribution",
        error_detail_json={"trace_id": "tr-fail"},
    )
    assert failure.batch_status == BatchStatus.COMPLETED_WITH_ERRORS
    assert failure.analysis_succeeded_count == 0
    assert failure.error_count == 1
    assert failure.error_code == "MODEL_TIMEOUT"

    with Session(engine) as session:
        run_row = session.get(CaseRun, case_run.id)
        assert run_row is not None
        assert run_row.status == CaseRunStatus.FAILED
        assert run_row.error_code == "MODEL_TIMEOUT"
        assert run_row.error_stage == "attribution"
        assert run_row.error_detail_json == {"trace_id": "tr-fail"}
        assert run_row.finished_at is not None
        case = _case_row(session, batch_id=batch_id, case_id="mvp_case_001")
        assert case.status == CaseStatus.PROCESSING_ERROR
        batch_run = session.scalar(
            select(BatchRun).where(BatchRun.run_id == "fail-batch-1")
        )
        assert batch_run is not None
        assert batch_run.error_count == 1


# ---------- 6. 启动恢复：中断标记与历史保留 ----------

def test_recover_interrupted_marks_and_preserves_history(
    run_store: RunStore, gateway, engine: Engine
) -> None:
    batch_id = _import_batch(gateway, batch_id="rcv")
    run_store.create_batch_run(batch_id=batch_id, run_id="rcv-batch-1", total_case_count=2)
    case_run_1 = run_store.create_case_run(
        batch_id=batch_id,
        case_id="mvp_case_001",
        run_id="rcv-cr-1",
        trigger_type=TriggerType.BATCH,
        batch_run_id="rcv-batch-1",
    )
    case_run_2 = run_store.create_case_run(
        batch_id=batch_id,
        case_id="mvp_case_002",
        run_id="rcv-cr-2",
        trigger_type=TriggerType.BATCH,
        batch_run_id="rcv-batch-1",
    )
    run_store.record_stage_started(
        case_run_id=case_run_1.id,
        stage_name="perception",
        status=CaseRunStatus.PERCEPTION_RUNNING,
    )
    summary = run_store.recover_interrupted()
    assert summary.interrupted_case_runs == 2
    assert summary.interrupted_batch_runs == 1
    assert summary.error_cases == 2
    assert summary.affected_batches == 1
    empty = run_store.recover_interrupted()
    assert empty.interrupted_case_runs == 0
    assert empty.interrupted_batch_runs == 0
    assert empty.error_cases == 0

    with Session(engine) as session:
        run_row = session.get(CaseRun, case_run_1.id)
        assert run_row is not None
        assert run_row.status == CaseRunStatus.INTERRUPTED
        assert run_row.error_code == APP_INTERRUPTED_CODE
        assert run_row.error_stage == APP_RECOVERY_STAGE
        assert run_row.finished_at is not None
        assert run_row.current_stage == "perception"  # 诊断信息保留
        run_row_2 = session.get(CaseRun, case_run_2.id)
        assert run_row_2 is not None
        assert run_row_2.status == CaseRunStatus.INTERRUPTED
        case = _case_row(session, batch_id=batch_id, case_id="mvp_case_001")
        assert case.status == CaseStatus.PROCESSING_ERROR
        batch = _batch_row(session, batch_id=batch_id)
        assert batch.status == BatchStatus.COMPLETED_WITH_ERRORS
        assert batch.error_count == 2
        batch_run = session.scalar(
            select(BatchRun).where(BatchRun.run_id == "rcv-batch-1")
        )
        assert batch_run is not None
        assert batch_run.status == BatchRunStatus.INTERRUPTED
        assert batch_run.finished_at is not None

    batch_history = run_store.batch_run_history(batch_id)
    assert [h.run_id for h in batch_history] == ["rcv-batch-1"]
    case_history = run_store.case_run_history(batch_id, "mvp_case_001")
    assert [h.run_id for h in case_history] == ["rcv-cr-1"]


# ---------- 7. 当前计数与历史不变性（首次统计 / MANUAL_RERUN） ----------

def test_manual_rerun_keeps_batch_history_and_counts(
    run_store: RunStore, gateway, engine: Engine
) -> None:
    batch_id = _import_batch(gateway, batch_id="rr", case_ids=("mvp_case_001",))
    batch_view = run_store.create_batch_run(
        batch_id=batch_id, run_id="rr-batch-1", total_case_count=1
    )
    case_run_1 = run_store.create_case_run(
        batch_id=batch_id,
        case_id="mvp_case_001",
        run_id="rr-cr-1",
        trigger_type=TriggerType.BATCH,
        batch_run_id=batch_view.run_id,
    )
    for stage_name in COMPLETE_PACKAGE_STAGES:
        run_store.record_stage_result(
            case_run_id=case_run_1.id,
            stage=_stage_input(stage_name, case_id="mvp_case_001"),
        )
    run_store.publish_complete_result(
        case_run_id=case_run_1.id,
        final_stage=_stage_input("strategy", case_id="mvp_case_001"),
        system_intervention_level="MUST_INTERVENE",
    )
    finished = run_store.finish_batch_run(
        batch_run_id=batch_view.id, status=BatchRunStatus.COMPLETED
    )
    assert finished.status == BatchRunStatus.COMPLETED
    assert finished.analysis_succeeded_count == 1
    assert finished.error_count == 0

    case_run_2 = run_store.create_case_run(
        batch_id=batch_id,
        case_id="mvp_case_001",
        run_id="rr-cr-2",
        trigger_type=TriggerType.MANUAL_RERUN,
    )
    assert case_run_2.previous_case_run_id == case_run_1.id
    assert case_run_2.batch_run_id is None
    with pytest.raises(ValueError):
        run_store.create_case_run(
            batch_id=batch_id,
            case_id="mvp_case_001",
            run_id="rr-cr-3",
            trigger_type=TriggerType.MANUAL_RERUN,
            batch_run_id="rr-batch-1",
        )

    with Session(engine) as session:
        batch_run = session.scalar(
            select(BatchRun).where(BatchRun.run_id == "rr-batch-1")
        )
        assert batch_run is not None
        assert batch_run.status == BatchRunStatus.COMPLETED
        assert batch_run.analysis_succeeded_count == 1
        assert batch_run.error_count == 0
        batch = _batch_row(session, batch_id=batch_id)
        assert batch.status == BatchStatus.ANALYZING  # 重跑让当前投影回到 ANALYZING
        old_run = session.get(CaseRun, case_run_1.id)
        assert old_run is not None
        assert old_run.status == CaseRunStatus.SUCCEEDED
        old_results = list(
            session.scalars(
                select(StageResult).where(StageResult.case_run_id == case_run_1.id)
            )
        )
        assert {r.stage_name for r in old_results} == set(COMPLETE_PACKAGE_STAGES)
        new_run = session.get(CaseRun, case_run_2.id)
        assert new_run is not None
        assert new_run.status == CaseRunStatus.STARTING
        assert new_run.previous_case_run_id == case_run_1.id
        assert new_run.batch_run_id is None

    batch_history = run_store.batch_run_history(batch_id)
    assert [h.run_id for h in batch_history] == ["rr-batch-1"]
    case_history = run_store.case_run_history(batch_id, "mvp_case_001")
    assert [h.run_id for h in case_history] == ["rr-cr-1", "rr-cr-2"]

