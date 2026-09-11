"""M3-05 测试用 Fake M1 RunStore、M2 分析引擎与运行查询。

Fake 返回 M1/M2 公开合同对象，M3 走完整编排，不让 Fake 绕过状态机或发布门槛。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

from app.contracts.analysis import (
    ActionType,
    AnalysisErrorCode,
    AnalysisFailure,
    AnalysisRequest,
    AnalysisStage,
    AnalysisSuccess,
    AttributionResult,
    BusinessCause,
    CaseInputV1Protocol,
    Cause,
    DecisionPackage,
    Emotion,
    EmotionAssessment,
    InterventionLevel,
    PerceptionEventItem,
    PerceptionResult,
    ResolutionStatus,
    StatementBasis,
    StrategyAction,
)
from app.modules.data.queries.views import (
    BatchWorkspaceView,
    CaseDetailView,
    CaseQueueItemView,
    CaseQueueView,
)
from app.modules.data.run_store.errors import ActiveRunConflictError
from app.modules.data.run_store.types import (
    BatchRunView,
    CaseRunView,
    FailureResult,
    PublishResult,
    RecoverySummary,
)

IMPORTED_AT = "2026-09-07T08:00:00+00:00"


def make_workspace(
    batch_id: str = "b1",
    *,
    status: str = "PENDING_ANALYSIS",
    case_count: int = 2,
    analysis_succeeded: int = 0,
    error_count: int = 0,
) -> BatchWorkspaceView:
    return BatchWorkspaceView(
        batch_id=batch_id,
        source_filename="mvp.zip",
        is_mock=True,
        status=status,
        case_count=case_count,
        evidence_count=3,
        analysis_succeeded_count=analysis_succeeded,
        error_count=error_count,
        imported_at=IMPORTED_AT,
        can_start_analysis=status == "PENDING_ANALYSIS",
        analysis_unavailable_message=None,
    )


def make_queue(batch_id: str = "b1", *, case_ids: list[str] | None = None) -> CaseQueueView:
    ids = case_ids or ["c1", "c2"]
    items = [
        CaseQueueItemView(
            case_id=cid,
            customer_display_id=f"客户-{cid}",
            is_high_value=True,
            status="PENDING_ANALYSIS",
            has_evidence_conflict=False,
            has_insufficient_evidence=False,
            has_modality_failure=False,
        )
        for cid in ids
    ]
    return CaseQueueView(items=items, total=len(items))


def make_success(case_id: str) -> AnalysisSuccess:
    evidence_id = "e1"
    perception = PerceptionResult(
        schema_version="v1",
        case_id=case_id,
        events=[
            PerceptionEventItem(
                event_no=1,
                category="物流延误",
                summary="客户反馈迟迟未收到货",
                statement_basis=StatementBasis.CUSTOMER_CLAIMED,
                resolution=ResolutionStatus.UNRESOLVED,
                evidence_ids=[evidence_id],
            )
        ],
        emotion=EmotionAssessment(value=Emotion.IMPATIENT, evidence_ids=[evidence_id]),
    )
    attribution = AttributionResult(
        schema_version="v1",
        case_id=case_id,
        risk_summary="高价值客户且商品问题明确",
        primary_cause=Cause(
            category=BusinessCause.LOGISTICS_FULFILLMENT,
            explanation="物流履约异常",
            evidence_ids=[evidence_id],
        ),
    )
    decision = DecisionPackage(
        schema_version="v1",
        case_id=case_id,
        intervention_level=InterventionLevel.MUST_INTERVENE,
        priority_reason="高价值客户且商品问题明确",
        actions=[
            StrategyAction(
                action_type=ActionType.CUSTOMER_CONTACT,
                description="建议人工联系客户",
                reason="高价值客户受影响",
                evidence_ids=[evidence_id],
            )
        ],
    )
    return AnalysisSuccess(
        status="SUCCESS", perception=perception, attribution=attribution, decision=decision
    )


def make_failure(case_id: str) -> AnalysisFailure:
    return AnalysisFailure(
        status="FAILED",
        error_code=AnalysisErrorCode.MODEL_TIMEOUT,
        error_stage=AnalysisStage.PERCEPTION,
        attempts_exhausted=True,
        trace_id="trace-1",
    )


class FakeEngine:
    """Fake M2 AnalysisEnginePort：按 case 返回成功或失败，记录请求与事件。"""

    def __init__(
        self,
        outcomes: dict[str, AnalysisSuccess | AnalysisFailure] | None = None,
    ) -> None:
        self.outcomes = outcomes or {}
        self.requests: list[AnalysisRequest] = []
        self.emitted_sinks: list[Any] = []
        self.closed = False

    def close(self) -> None:
        self.closed = True

    def analyze_case(
        self, request: AnalysisRequest, event_sink
    ) -> AnalysisSuccess | AnalysisFailure:
        self.requests.append(request)
        self.emitted_sinks.append(event_sink)
        case_id = request.case_input.case_id
        outcome = self.outcomes.get(case_id)
        if outcome is None:
            outcome = make_success(case_id)
        return outcome


class FakeRunStore:
    """Fake M1 RunStorePort：记录调用序列供断言，可配置活动批次冲突。"""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.model_attempts: list[tuple[int, Any]] = []
        self.case_run_id = 0
        self.reject_start = False
        self.reject_case = False
        self.published = 0
        self.failed = 0

    def create_batch_run(
        self, *, batch_id, run_id, total_case_count, batch_status=None, started_at=None
    ) -> BatchRunView:
        self.calls.append(f"create_batch_run:{batch_id}")
        if self.reject_start:
            raise ActiveRunConflictError(object_type="batch", object_id=batch_id)
        return BatchRunView(
            id=1, run_id=run_id, batch_id=batch_id, status="STARTING",
            total_case_count=total_case_count, analysis_succeeded_count=0,
            error_count=0, started_at=IMPORTED_AT, finished_at=None,
        )

    def create_case_run(
        self,
        *,
        batch_id,
        case_id,
        run_id,
        trigger_type,
        batch_run_id=None,
        case_status=None,
        run_status=None,
        started_at=None,
    ) -> CaseRunView:
        if self.reject_case:
            raise ActiveRunConflictError(object_type="case", object_id=case_id)
        self.case_run_id += 1
        self.calls.append(f"create_case_run:{case_id}")
        return CaseRunView(
            id=self.case_run_id, run_id=run_id, batch_id=batch_id, case_id=case_id,
            trigger_type=str(trigger_type), status="STARTING", current_stage=None,
            previous_case_run_id=None, batch_run_id=batch_run_id,
            started_at=IMPORTED_AT, finished_at=None,
        )

    def record_stage_started(self, *, case_run_id, stage_name, status, occurred_at=None) -> None:
        self.calls.append(f"stage_started:{case_run_id}:{stage_name}")

    def record_model_attempt(self, *, case_run_id, attempt) -> None:
        self.calls.append(f"model_attempt:{case_run_id}")
        self.model_attempts.append((case_run_id, attempt))

    def record_stage_result(self, *, case_run_id, stage, occurred_at=None) -> None:
        self.calls.append(f"stage_result:{case_run_id}:{stage.stage_name}")

    def record_failure(
        self, *, case_run_id, error_code, error_stage, error_detail_json=None,
        case_status=None, run_status=None, occurred_at=None
    ) -> FailureResult:
        self.failed += 1
        self.calls.append(f"failure:{case_run_id}:{error_code}")
        return FailureResult(
            case_run_id=case_run_id, run_id="r", batch_id="b1", case_id="c",
            error_code=error_code, batch_status="COMPLETED_WITH_ERRORS",
            analysis_succeeded_count=1, error_count=1,
        )

    def publish_complete_result(
        self, *, case_run_id, final_stage, system_intervention_level=None,
        case_status=None, run_status=None, occurred_at=None
    ) -> PublishResult:
        self.published += 1
        self.calls.append(f"publish:{case_run_id}:{system_intervention_level}")
        return PublishResult(
            case_run_id=case_run_id, run_id="r", batch_id="b1", case_id="c",
            batch_status="COMPLETED", analysis_succeeded_count=1, error_count=0,
        )

    def finish_batch_run(self, *, batch_run_id, status, finished_at=None) -> BatchRunView:
        self.calls.append(f"finish:{batch_run_id}:{status}")
        return BatchRunView(
            id=batch_run_id, run_id="r", batch_id="b1", status=str(status),
            total_case_count=2, analysis_succeeded_count=1, error_count=0,
            started_at=IMPORTED_AT, finished_at=IMPORTED_AT,
        )

    def recover_interrupted(self, *, now=None) -> RecoverySummary:
        self.calls.append("recover")
        return RecoverySummary(
            interrupted_case_runs=0, interrupted_batch_runs=0, error_cases=0, affected_batches=0
        )


class FakeRunQuery:
    """Fake RunQueryPort：返回批次/队列投影与 CaseInput 替身。"""

    def __init__(
        self,
        *,
        workspace: BatchWorkspaceView | None = None,
        queue: CaseQueueView | None = None,
        run_store: FakeRunStore | None = None,
        detail: CaseDetailView | None = None,
        current_case_run_id: int | None = None,
    ) -> None:
        self.workspace = workspace or make_workspace()
        self.queue = queue or make_queue()
        self.detail = detail
        self.current_case_run_id = current_case_run_id
        self.missing = set()
        self._run_store = run_store

    def get_batch(self, batch_id: str) -> BatchWorkspaceView:
        if self.workspace.batch_id != batch_id:
            raise LookupError(f"批次不存在: {batch_id}")
        if self._run_store is not None:
            return self.workspace.model_copy(
                update={
                    "analysis_succeeded_count": self._run_store.published,
                    "error_count": self._run_store.failed,
                }
            )
        return self.workspace

    def list_cases(
        self, batch_id: str, *, limit: int | None = None, offset: int | None = None
    ) -> CaseQueueView:
        return self.queue

    def get_case_detail(self, batch_id: str, case_id: str) -> CaseDetailView:
        detail = self.detail
        if detail is None or detail.batch_id != batch_id or detail.case_id != case_id:
            raise LookupError(f"案例不存在: {batch_id}/{case_id}")
        return detail

    def get_current_case_run_id(self, batch_id: str, case_id: str) -> int | None:
        return self.current_case_run_id

    def get_case_input(self, batch_id: str, case_id: str) -> CaseInputV1Protocol | None:
        if case_id in self.missing:
            return None
        return cast(
            CaseInputV1Protocol,
            SimpleNamespace(case_id=case_id, batch_id=batch_id),
        )


def make_detail(
    *, batch_id: str = "b1", case_id: str = "c1", status: str = "PENDING_REVIEW"
) -> CaseDetailView:
    return CaseDetailView(
        batch_id=batch_id,
        case_id=case_id,
        customer_display_id=f"客户-{case_id}",
        is_high_value=True,
        customer_value_summary="高价值客户：测试",
        status=status,
        is_mock=True,
        can_rerun=True,
        can_review=status == "PENDING_REVIEW",
    )


def make_versions() -> dict[str, str]:
    return {
        "perception_contract_version": "v1",
        "attribution_contract_version": "v1",
        "strategy_contract_version": "v1",
        "perception_prompt_version": "v1",
        "attribution_prompt_version": "v1",
        "strategy_prompt_version": "v1",
        "action_catalog_version": "v1",
    }
