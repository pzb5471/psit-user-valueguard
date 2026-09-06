"""各阶段响应 JSON Schema 的唯一来源（M2-02，规格第 9.2 节）。

Schema 只能从 backend/app/contracts/analysis.py 的阶段结果 Pydantic 模型生成；
本模块不复制、不手写任何字段表，避免 Prompt 与合同漂移（M2-02 禁止事项）。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.contracts.analysis import (
    AnalysisStage,
    AttributionResult,
    DecisionPackage,
    PerceptionResult,
)

_STAGE_RESULT_MODELS: dict[AnalysisStage, type[BaseModel]] = {
    AnalysisStage.PERCEPTION: PerceptionResult,
    AnalysisStage.ATTRIBUTION: AttributionResult,
    AnalysisStage.STRATEGY: DecisionPackage,
}


def response_schema_for(stage: AnalysisStage) -> dict[str, Any]:
    """返回指定阶段响应合同的 JSON Schema（由 Pydantic 从冻结合同生成）。"""
    try:
        model = _STAGE_RESULT_MODELS[stage]
    except KeyError as error:
        raise ValueError(f"未知分析阶段：{stage!r}") from error
    return model.model_json_schema()
