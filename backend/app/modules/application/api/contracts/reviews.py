"""人工确认请求合同（技术实施规格 12.3；ADR 0075、0076）。

四种请求共同携带 submission_id、review_token 和 outcome，按 outcome
判别联合；每种变体只声明自己允许的字段，extra="forbid" 使"禁止"字段
（如 APPROVED 携带另一份人工结果、INSUFFICIENT_EVIDENCE 携带确定原因）
在请求校验阶段直接被拒绝。submission_id 由前端为一次业务提交生成 UUID，
网络重试必须复用；幂等语义由 M3-07 的存储与状态机执行。
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.contracts.analysis import ActionType, BusinessCause, InterventionLevel

__all__ = [
    "ApprovedReviewRequest",
    "InsufficientEvidenceReviewRequest",
    "ModifiedApprovedReviewRequest",
    "RejectedWithJudgmentReviewRequest",
    "ReviewOutcome",
    "ReviewRequest",
]


class ReviewOutcome(StrEnum):
    """人工确认结果（规格 7.2）。"""

    APPROVED = "APPROVED"
    MODIFIED_AND_APPROVED = "MODIFIED_AND_APPROVED"
    REJECTED_WITH_JUDGMENT = "REJECTED_WITH_JUDGMENT"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class _ReviewBase(BaseModel):
    """四种请求的共同字段。"""

    model_config = ConfigDict(extra="forbid")

    submission_id: UUID
    review_token: str = Field(min_length=1)


class ApprovedReviewRequest(_ReviewBase):
    """直接通过：只携带共同字段，禁止另一份人工结果和审核原因。"""

    outcome: Literal[ReviewOutcome.APPROVED]


class ModifiedApprovedReviewRequest(_ReviewBase):
    """修改后确认：必须给出完整人工判断与修改原因，执行说明按需。"""

    outcome: Literal[ReviewOutcome.MODIFIED_AND_APPROVED]
    final_intervention_level: InterventionLevel
    final_cause: BusinessCause
    final_actions: list[ActionType] = Field(min_length=1)
    review_reason: str = Field(min_length=1)
    execution_note: str | None = None


class RejectedWithJudgmentReviewRequest(_ReviewBase):
    """驳回并给出判断：必须携带人工判断与驳回原因，不得只有驳回。"""

    outcome: Literal[ReviewOutcome.REJECTED_WITH_JUDGMENT]
    final_intervention_level: InterventionLevel
    final_cause: BusinessCause
    final_actions: list[ActionType] = Field(min_length=1)
    review_reason: str = Field(min_length=1)
    execution_note: str | None = None


class InsufficientEvidenceReviewRequest(_ReviewBase):
    """标记证据不足：只说明证据缺口，禁止确定原因和处理动作。"""

    outcome: Literal[ReviewOutcome.INSUFFICIENT_EVIDENCE]
    review_reason: str = Field(min_length=1)


ReviewRequest = Annotated[
    ApprovedReviewRequest
    | ModifiedApprovedReviewRequest
    | RejectedWithJudgmentReviewRequest
    | InsufficientEvidenceReviewRequest,
    Field(discriminator="outcome"),
]
