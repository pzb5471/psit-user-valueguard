"""M2 分析模块感知阶段子包（M2-05）：感知输入构造器与阶段执行器。"""

from app.modules.analysis.perception.executor import (
    PerceptionStageResult,
    run_perception_stage,
    validate_perception_response,
)
from app.modules.analysis.perception.input_builder import (
    ImageResolver,
    PerceptionStageInput,
    build_perception_request,
    citable_evidence_ids,
)

__all__ = [
    "ImageResolver",
    "PerceptionStageInput",
    "PerceptionStageResult",
    "build_perception_request",
    "citable_evidence_ids",
    "run_perception_stage",
    "validate_perception_response",
]
