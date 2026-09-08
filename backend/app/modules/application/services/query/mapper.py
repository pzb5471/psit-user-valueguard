"""M1 数据端口投影 → M3 对外业务 DTO 的显式类型映射（M3-04；规格 12.2）。

M3 只面对 M1 的公开端口投影对象（跨模块合同对象），在服务层把它转换为对外
OpenAPI 真源的 API DTO。M1 投影的字符串字段在此显式转为 M3 API 枚举/
datetime，避免依赖 Pydantic 宽松转换；证据模态大小写差异也在此落地。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.contracts.analysis import (
    ActionType,
    AttributionFallbackCause,
    BusinessCause,
    InterventionLevel,
)
from app.contracts.states import BatchStatus, CaseStatus
from app.modules.application.api.contracts.errors import (
    CaseProcessingErrorCode,
    ProcessingErrorStage,
)
from app.modules.application.api.contracts.views import (
    ActionView,
    BatchListView,
    BatchWorkspaceView,
    CaseDetailView,
    CaseProcessingErrorView,
    CaseQueueItemView,
    CaseQueueView,
    CauseView,
    CitedEvidenceView,
    EvidenceModality,
    OptionItem,
    ReviewOptionsView,
    ReviewResultView,
)
from app.modules.data.queries.views import (
    BatchListView as DataBatchListView,
)
from app.modules.data.queries.views import (
    BatchWorkspaceView as DataBatchWorkspaceView,
)
from app.modules.data.queries.views import (
    CaseDetailView as DataCaseDetailView,
)
from app.modules.data.queries.views import (
    CaseProcessingErrorView as DataCaseProcessingErrorView,
)
from app.modules.data.queries.views import (
    CaseQueueItemView as DataCaseQueueItemView,
)
from app.modules.data.queries.views import (
    CaseQueueView as DataCaseQueueView,
)
from app.modules.data.queries.views import (
    CitedEvidenceView as DataCitedEvidenceView,
)
from app.modules.data.queries.views import (
    OptionItem as DataOptionItem,
)
from app.modules.data.queries.views import (
    ReviewOptionsView as DataReviewOptionsView,
)
from app.modules.data.queries.views import (
    ReviewResultView as DataReviewResultView,
)

_MODALITY_MAP = {
    "text": EvidenceModality.TEXT,
    "image": EvidenceModality.IMAGE,
    "behavior": EvidenceModality.BEHAVIOR,
}


def _datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _intervention(value: str | None) -> InterventionLevel | None:
    return InterventionLevel(value) if value is not None else None


def _cause_category(value: Any) -> BusinessCause | AttributionFallbackCause:
    if value == AttributionFallbackCause.INSUFFICIENT_EVIDENCE.value:
        return AttributionFallbackCause.INSUFFICIENT_EVIDENCE
    return BusinessCause(value)


def _cause(data: dict[str, Any]) -> CauseView:
    counter = data.get("counter_evidence_ids")
    uncertainty = data.get("uncertainty")
    return CauseView(
        category=_cause_category(data.get("category")),
        explanation=str(data.get("explanation") or ""),
        evidence_ids=list(data.get("evidence_ids") or []),
        counter_evidence_ids=list(counter) if counter is not None else None,
        uncertainty=str(uncertainty) if uncertainty is not None else None,
    )


def _action(data: dict[str, Any]) -> ActionView:
    precondition = data.get("precondition")
    return ActionView(
        action_type=ActionType(data.get("action_type")),
        description=str(data.get("description") or ""),
        reason=str(data.get("reason") or ""),
        evidence_ids=list(data.get("evidence_ids") or []),
        precondition=str(precondition) if precondition is not None else None,
    )


def to_batch_workspace(view: DataBatchWorkspaceView) -> BatchWorkspaceView:
    return BatchWorkspaceView(
        batch_id=view.batch_id,
        source_filename=view.source_filename,
        is_mock=view.is_mock,
        status=BatchStatus(view.status),
        case_count=view.case_count,
        evidence_count=view.evidence_count,
        analysis_succeeded_count=view.analysis_succeeded_count,
        error_count=view.error_count,
        imported_at=_datetime(view.imported_at),
        can_start_analysis=view.can_start_analysis,
        analysis_unavailable_message=view.analysis_unavailable_message,
    )


def to_batch_list(view: DataBatchListView) -> BatchListView:
    return BatchListView(
        items=[to_batch_workspace(item) for item in view.items],
        total=view.total,
    )


def to_case_queue_item(view: DataCaseQueueItemView) -> CaseQueueItemView:
    return CaseQueueItemView(
        case_id=view.case_id,
        customer_display_id=view.customer_display_id,
        is_high_value=view.is_high_value,
        risk_summary=view.risk_summary,
        intervention_level=_intervention(view.intervention_level),
        priority_reason=view.priority_reason,
        status=CaseStatus(view.status),
        has_evidence_conflict=view.has_evidence_conflict,
        has_insufficient_evidence=view.has_insufficient_evidence,
        has_modality_failure=view.has_modality_failure,
    )


def to_case_queue(view: DataCaseQueueView) -> CaseQueueView:
    return CaseQueueView(
        items=[to_case_queue_item(item) for item in view.items],
        total=view.total,
    )


def _to_option(item: DataOptionItem) -> OptionItem:
    return OptionItem(value=item.value, label=item.label)


def _to_review_options(view: DataReviewOptionsView | None) -> ReviewOptionsView | None:
    if view is None:
        return None
    return ReviewOptionsView(
        intervention_levels=[_to_option(item) for item in view.intervention_levels],
        cause_categories=[_to_option(item) for item in view.cause_categories],
        action_catalog_version=view.action_catalog_version,
        action_types=[_to_option(item) for item in view.action_types],
    )


def _to_cited(view: DataCitedEvidenceView) -> CitedEvidenceView:
    return CitedEvidenceView(
        evidence_id=view.evidence_id,
        modality=_MODALITY_MAP[view.modality],
        label=view.label,
        text=view.text,
        summary=view.summary,
    )


def _to_review(view: DataReviewResultView) -> ReviewResultView:
    final_actions = (
        [_action(action) for action in view.final_actions]
        if view.final_actions is not None
        else None
    )
    return ReviewResultView(
        outcome=view.outcome,
        final_intervention_level=_intervention(view.final_intervention_level),
        final_cause=_cause(view.final_cause) if view.final_cause else None,
        final_actions=final_actions,
        execution_note=view.execution_note,
        review_reason=view.review_reason,
        created_at=_datetime(view.created_at),
    )


def _to_processing(view: DataCaseProcessingErrorView) -> CaseProcessingErrorView:
    return CaseProcessingErrorView(
        code=CaseProcessingErrorCode(view.code),
        message=view.message,
        stage=ProcessingErrorStage(view.stage),
        next_action=view.next_action,
        trace_id=view.trace_id,
    )


def to_case_detail(view: DataCaseDetailView) -> CaseDetailView:
    actions = [_action(action) for action in view.actions] if view.actions is not None else None
    cited = [_to_cited(item) for item in view.cited_evidence] if view.cited_evidence else None
    return CaseDetailView(
        batch_id=view.batch_id,
        case_id=view.case_id,
        customer_display_id=view.customer_display_id,
        is_high_value=view.is_high_value,
        customer_value_summary=view.customer_value_summary,
        status=CaseStatus(view.status),
        intervention_level=_intervention(view.intervention_level),
        risk_summary=view.risk_summary,
        primary_cause=_cause(view.primary_cause) if view.primary_cause else None,
        actions=actions,
        communication_points=view.communication_points,
        uncertainty=view.uncertainty,
        missing_evidence=view.missing_evidence,
        cited_evidence=cited,
        is_mock=view.is_mock,
        review_result=_to_review(view.review_result) if view.review_result else None,
        processing_error=_to_processing(view.processing_error) if view.processing_error else None,
        can_rerun=view.can_rerun,
        can_review=view.can_review,
        review_token=view.review_token,
        review_options=_to_review_options(view.review_options),
    )
