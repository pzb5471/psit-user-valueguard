"""校验器结构化错误（M2-04，规格第 9.4 节）。

错误码对应规格第 9.4 节校验顺序的失败类别；repairable 标记供 M2-08 引擎
区分可定向修复的结构问题（一次修复请求可解决）与不可重试的污染问题
（密封答案字段名进入结果，直接判阶段失败）。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.contracts.analysis import AnalysisStage

__all__ = ["StageValidationError", "ValidationErrorCode"]


class ValidationErrorCode(StrEnum):
    """阶段结果校验失败的稳定错误类别（规格第 9.4 节步骤 1—7）。"""

    JSON_PARSE_FAILED = "JSON_PARSE_FAILED"
    SCHEMA_VALIDATION_FAILED = "SCHEMA_VALIDATION_FAILED"
    CASE_ID_MISMATCH = "CASE_ID_MISMATCH"
    EVIDENCE_NOT_ALLOWED = "EVIDENCE_NOT_ALLOWED"
    CROSS_STAGE_REFERENCE_INVALID = "CROSS_STAGE_REFERENCE_INVALID"
    FORBIDDEN_CONTENT = "FORBIDDEN_CONTENT"
    ACTION_CATALOG_VIOLATION = "ACTION_CATALOG_VIOLATION"
    MINIMUM_INTERVENTION_VIOLATION = "MINIMUM_INTERVENTION_VIOLATION"
    IMAGE_COVERAGE_INCOMPLETE = "IMAGE_COVERAGE_INCOMPLETE"


@dataclass(frozen=True)
class StageValidationError:
    """单条校验失败：阶段、字段路径、可读消息与是否可定向修复。"""

    code: ValidationErrorCode
    stage: AnalysisStage
    field_path: str
    message: str
    repairable: bool

    def to_dict(self) -> dict[str, str | bool]:
        return {
            "code": self.code.value,
            "stage": self.stage.value,
            "field_path": self.field_path,
            "message": self.message,
            "repairable": self.repairable,
        }
