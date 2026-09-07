"""M2 分析模块归因阶段子包（M2-06）：归因输入构造器与阶段执行器。"""

from app.modules.analysis.attribution.executor import (
    AttributionStageResult,
    ModelAttemptRecord,
    run_attribution_stage,
)
from app.modules.analysis.attribution.input_builder import (
    AttributionStageInput,
    build_attribution_request,
    cited_ids_in_order,
)

__all__ = [
    "AttributionStageInput",
    "AttributionStageResult",
    "ModelAttemptRecord",
    "build_attribution_request",
    "cited_ids_in_order",
    "run_attribution_stage",
]
