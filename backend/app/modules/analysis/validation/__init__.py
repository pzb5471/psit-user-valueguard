"""M2 分析模块严格校验子包（M2-04）：三阶段结果校验器、结构化错误与上下文。"""

from app.modules.analysis.validation.errors import (
    StageValidationError,
    ValidationErrorCode,
)
from app.modules.analysis.validation.validator import (
    AttributionValidationContext,
    PerceptionValidationContext,
    StageValidationOutcome,
    StrategyValidationContext,
    perception_cited_evidence_ids,
    validate_stage_result,
)

__all__ = [
    "AttributionValidationContext",
    "PerceptionValidationContext",
    "StageValidationError",
    "StageValidationOutcome",
    "StrategyValidationContext",
    "ValidationErrorCode",
    "perception_cited_evidence_ids",
    "validate_stage_result",
]
