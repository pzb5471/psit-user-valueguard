"""M3-07 ReviewService：人工确认编排（技术实施规格 7.2、10.2、12.3）。

只负责：取当前案例运行的内部 id、把 API 四种命令转成 M1 ReviewSubmitInput、
调用 M1 ReviewStore 并映射稳定错误与结果视图。幂等、Token 并发保护、字段
规则、已完成只读由 M1 ReviewStore 在单事务内完成（M1-08 契约）；M3 不透传
异常、ORM 或供应商细节。review_token 不可读、不展示（规格 12.3）。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from app.contracts.analysis import (
    ActionType,
    AttributionFallbackCause,
    BusinessCause,
    InterventionLevel,
)
from app.modules.application.api.contracts.errors import ApiErrorCode
from app.modules.application.api.contracts.reviews import (
    ApprovedReviewRequest,
    InsufficientEvidenceReviewRequest,
    ReviewRequest,
)
from app.modules.application.api.contracts.views import (
    ActionView,
    CauseView,
    ReviewResultView,
)
from app.modules.application.review.ports import ReviewStorePort
from app.modules.application.run_service.ports import RunQueryPort
from app.modules.application.services.query.errors import ServiceError
from app.modules.data.queries.views import ReviewResultView as DataReviewResultView
from app.modules.data.review_store import (
    CaseAlreadyCompletedError,
    ReviewFieldValidationError,
    ReviewStoreResourceNotFoundError,
    ReviewSubmitInput,
    StaleCaseResultError,
)


def _catalog_action_labels() -> dict[str, str]:
    root = Path(__file__).resolve()
    for candidate in root.parents:
        catalog = candidate / "config" / "action_catalog.v1.json"
        if catalog.is_file():
            data = json.loads(catalog.read_text(encoding="utf-8"))
            return {
                item["action_type"]: item["description"] for item in data["actions"]
            }
    return {}


_ACTION_LABELS = _catalog_action_labels()


def _to_submit(request: ReviewRequest) -> ReviewSubmitInput:
    """把四种 API 请求命令映射为 M1 ReviewSubmitInput 载荷（规格 12.3 形态）。"""
    outcome = request.outcome.value
    if isinstance(request, ApprovedReviewRequest):
        return ReviewSubmitInput(outcome=outcome)
    if isinstance(request, InsufficientEvidenceReviewRequest):
        return ReviewSubmitInput(outcome=outcome, review_reason=request.review_reason)
    return ReviewSubmitInput(
        outcome=outcome,
        final_intervention_level=request.final_intervention_level.value,
        final_cause={"cause_category": request.final_cause.value},
        final_actions=[{"action_type": action.value} for action in request.final_actions],
        review_reason=request.review_reason,
        execution_note=request.execution_note,
    )


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _to_api(view: DataReviewResultView) -> ReviewResultView:
    final_actions = None
    if view.final_actions is not None:
        final_actions = [
            ActionView(
                action_type=ActionType(item["action_type"]),
                description=_ACTION_LABELS.get(
                    item["action_type"], str(item["action_type"])
                ),
                reason="人工确认选定的处理动作",
            )
            for item in view.final_actions
            if isinstance(item, dict) and item.get("action_type")
        ]
    final_cause = None
    if view.final_cause is not None:
        category = view.final_cause.get("cause_category")
        if category:
            if category == AttributionFallbackCause.INSUFFICIENT_EVIDENCE.value:
                cause: BusinessCause | AttributionFallbackCause = (
                    AttributionFallbackCause.INSUFFICIENT_EVIDENCE
                )
            else:
                cause = BusinessCause(category)
            final_cause = CauseView(category=cause, explanation="人工确认原因")
    return ReviewResultView(
        outcome=view.outcome,
        final_intervention_level=(
            InterventionLevel(view.final_intervention_level)
            if view.final_intervention_level is not None
            else None
        ),
        final_cause=final_cause,
        final_actions=final_actions,
        execution_note=view.execution_note,
        review_reason=view.review_reason,
        created_at=_parse_iso(view.created_at),
    )


class ReviewService:
    """人工确认服务；以显式端口注入构造。"""

    def __init__(self, *, query: RunQueryPort, review_store: ReviewStorePort) -> None:
        self._query = query
        self._review_store = review_store

    def submit_review(
        self, batch_id: str, case_id: str, request: ReviewRequest
    ) -> ReviewResultView:
        case_run_id = self._query.get_current_case_run_id(batch_id, case_id)
        if case_run_id is None:
            raise ServiceError(
                ApiErrorCode.RESOURCE_NOT_FOUND,
                f"案例不存在或无当前运行：{batch_id}/{case_id}",
                object_type="case",
                object_id=case_id,
            )
        try:
            view = self._review_store.submit_review(
                submission_id=str(request.submission_id),
                case_run_id=case_run_id,
                review_token=request.review_token,
                payload=_to_submit(request),
            )
        except ReviewStoreResourceNotFoundError as error:
            raise ServiceError(
                ApiErrorCode.RESOURCE_NOT_FOUND,
                getattr(error, "message", str(error)) or "资源不存在",
                object_type=getattr(error, "object_type", "case"),
                object_id=getattr(error, "object_id", case_id),
            ) from None
        except StaleCaseResultError as error:
            raise ServiceError(
                ApiErrorCode.STALE_CASE_RESULT,
                "审核令牌已失效，请刷新案例后重试",
                object_type="case",
                object_id=case_id,
            ) from error
        except CaseAlreadyCompletedError as error:
            raise ServiceError(
                ApiErrorCode.CASE_ALREADY_COMPLETED,
                "案例已完成或已有审核结果",
                object_type="case",
                object_id=case_id,
            ) from error
        except ReviewFieldValidationError as error:
            raise ServiceError(
                ApiErrorCode.REQUEST_VALIDATION_FAILED,
                getattr(error, "message", "审核请求不合格"),
                object_type="review",
                object_id=case_id,
            ) from error
        return _to_api(view)
