"""策略阶段输入构造器（M2-07，规格第 9.2 节阶段最小权限）。

只携带两阶段结构化结果、高价值结论、动作目录与获准引用证据内容；
不重发原图和完整原始对话，不读取 RFM 数值、权重、阈值和计算过程。
获准引用顺序为感知结果首次引用顺序 + 归因新增引用顺序，保证同输入
产出完全相同的请求与请求清单。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass

from app.contracts.analysis import (
    AnalysisStage,
    AttributionResult,
    PerceptionResult,
)
from app.modules.analysis.attribution import cited_ids_in_order
from app.modules.analysis.client import GlmRequest
from app.modules.analysis.prompts import StagePrompt

__all__ = [
    "ActionCatalogEntry",
    "ActionCatalogView",
    "HighValueConclusion",
    "StrategyStageInput",
    "build_strategy_request",
    "upstream_cited_ids",
]


@dataclass(frozen=True)
class HighValueConclusion:
    """高价值客户结论（规格第 5.5 节）：Agent 只读取结论，不读取 RFM 过程。"""

    is_high_value: bool
    decision_reason: str


@dataclass(frozen=True)
class ActionCatalogEntry:
    """动作目录条目：动作代码与业务含义（规格第 7.3 节）。"""

    action_type: str
    description: str


@dataclass(frozen=True)
class ActionCatalogView:
    """动作目录视图：由装配方从 config/action_catalog.v1.json 构造后传入。"""

    catalog_version: str
    actions: tuple[ActionCatalogEntry, ...]


class StrategyStageInput:
    """策略阶段获准输入：两阶段结果、高价值结论、动作目录与获准证据内容。"""

    __slots__ = (
        "perception",
        "attribution",
        "high_value_conclusion",
        "action_catalog",
        "evidence_content",
    )

    def __init__(
        self,
        *,
        perception: PerceptionResult,
        attribution: AttributionResult,
        high_value_conclusion: HighValueConclusion,
        action_catalog: ActionCatalogView,
        evidence_content: Mapping[str, str],
    ) -> None:
        self.perception = perception
        self.attribution = attribution
        self.high_value_conclusion = high_value_conclusion
        self.action_catalog = action_catalog
        self.evidence_content = dict(evidence_content)


def upstream_cited_ids(
    perception: PerceptionResult, attribution: AttributionResult
) -> tuple[str, ...]:
    """两阶段实际引用的全部证据编号（感知首次引用顺序 + 归因新增，去重保序）。"""

    ordered: list[str] = []
    seen: set[str] = set()

    def remember(evidence_id: str) -> None:
        if evidence_id not in seen:
            seen.add(evidence_id)
            ordered.append(evidence_id)

    for evidence_id in cited_ids_in_order(perception):
        remember(evidence_id)
    causes = [attribution.primary_cause]
    if attribution.alternative_cause is not None:
        causes.append(attribution.alternative_cause)
    for cause in causes:
        for evidence_id in cause.evidence_ids:
            remember(evidence_id)
        if cause.counter_evidence_ids is not None:
            for evidence_id in cause.counter_evidence_ids:
                remember(evidence_id)
    return tuple(ordered)


def build_strategy_request(
    stage_input: StrategyStageInput, *, prompt: StagePrompt
) -> GlmRequest:
    """构造策略阶段模型请求；获准证据内容缺失时立即失败，不静默省略。"""

    image_ids = {
        observation.image_evidence_id
        for observation in stage_input.perception.image_observations
    }
    cited = [
        evidence_id
        for evidence_id in upstream_cited_ids(
            stage_input.perception, stage_input.attribution
        )
        if evidence_id not in image_ids
    ]
    missing = [
        evidence_id
        for evidence_id in cited
        if evidence_id not in stage_input.evidence_content
    ]
    if missing:
        raise ValueError(f"缺少获准引用证据内容：{'、'.join(missing)}")

    sections: list[str] = [
        "当前案例感知阶段结果（JSON）：",
        json.dumps(
            stage_input.perception.model_dump(mode="json", exclude_none=True),
            ensure_ascii=False,
        ),
        "当前案例归因阶段结果（JSON）：",
        json.dumps(
            stage_input.attribution.model_dump(mode="json", exclude_none=True),
            ensure_ascii=False,
        ),
        "高价值客户结论：",
        f"is_high_value: {stage_input.high_value_conclusion.is_high_value}",
        f"decision_reason: {stage_input.high_value_conclusion.decision_reason}",
        f"动作目录（catalog_version: {stage_input.action_catalog.catalog_version}，"
        "动作只能从目录内选择）：",
    ]
    sections.extend(
        f"- {entry.action_type}：{entry.description}"
        for entry in stage_input.action_catalog.actions
    )
    sections.append("获准引用的证据内容（只可引用两阶段结果中出现过的证据编号）：")
    sections.extend(
        f"[{evidence_id}] {stage_input.evidence_content[evidence_id]}"
        for evidence_id in cited
    )
    return GlmRequest(
        stage=AnalysisStage.STRATEGY,
        prompt_version=prompt.version,
        system_prompt=prompt.rendered_text,
        user_content="\n".join(sections),
    )
