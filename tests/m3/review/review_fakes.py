"""M3-07 测试用 Fake ReviewStorePort：记录提交并返回/抛出可配置结果。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.modules.data.queries.views import (
    ReviewResultView,
)
from app.modules.data.review_store.errors import (
    CaseAlreadyCompletedError,
    ReviewFieldValidationError,
    StaleCaseResultError,
)

IMPORTED_AT = "2026-09-07T09:00:00+00:00"


@dataclass
class FakeReviewStore:
    """Fake ReviewStorePort：幂等按 submission_id；可配置返回结果或抛出错误。"""

    result: ReviewResultView | None = None
    error: BaseException | None = None
    submissions: list[dict[str, Any]] = field(default_factory=list)

    def submit_review(
        self,
        *,
        submission_id: str,
        case_run_id: int,
        review_token: str,
        payload,
        case_status=None,
        occurred_at=None,
    ) -> ReviewResultView:
        self.submissions.append(
            {
                "submission_id": submission_id,
                "case_run_id": case_run_id,
                "review_token": review_token,
                "payload": payload,
            }
        )
        if self.error is not None:
            raise self.error
        if self.result is not None:
            return self.result
        return make_result(payload.outcome)


def make_result(
    outcome: str,
    *,
    final_intervention_level: str | None = None,
    cause_category: str | None = None,
    action_types: list[str] | None = None,
) -> ReviewResultView:
    return ReviewResultView(
        outcome=outcome,
        final_intervention_level=final_intervention_level,
        final_cause=({"cause_category": cause_category} if cause_category else None),
        final_actions=([{"action_type": a} for a in action_types] if action_types else None),
        execution_note=None,
        review_reason=None,
        created_at=IMPORTED_AT,
    )


def stale_result_error() -> StaleCaseResultError:
    return StaleCaseResultError(object_id="case_run-1")


def completed_error() -> CaseAlreadyCompletedError:
    return CaseAlreadyCompletedError(object_id="case-1")


def validation_error() -> ReviewFieldValidationError:
    return ReviewFieldValidationError(message="审核请求不合格")
