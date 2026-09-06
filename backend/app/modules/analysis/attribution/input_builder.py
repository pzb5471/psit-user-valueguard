"""归因阶段输入构造器（M2-06，规格第 9.2 节阶段最小权限）。

只携带 PerceptionResult 与其中实际引用的证据内容；不重发原图和完整对话，
不读取高价值结论、RFM、动作目录或策略结果。获准引用顺序取感知结果的
首次引用顺序，保证同输入产出完全相同的请求与请求清单。
"""

from __future__ import annotations

import json
from collections.abc import Mapping

from app.contracts.analysis import AnalysisStage, PerceptionResult
from app.modules.analysis.client import GlmRequest
from app.modules.analysis.prompts import StagePrompt

__all__ = ["AttributionStageInput", "build_attribution_request"]


class AttributionStageInput:
    """归因阶段获准输入：感知结果 + 获准引用证据的已脱敏单行内容。"""

    __slots__ = ("perception", "evidence_content")

    def __init__(
        self,
        *,
        perception: PerceptionResult,
        evidence_content: Mapping[str, str],
    ) -> None:
        self.perception = perception
        self.evidence_content = dict(evidence_content)


def cited_ids_in_order(perception: PerceptionResult) -> tuple[str, ...]:
    """感知结果首次引用顺序的全部证据编号（去重、保序、确定性）。"""

    ordered: list[str] = []
    seen: set[str] = set()

    def remember(evidence_id: str) -> None:
        if evidence_id not in seen:
            seen.add(evidence_id)
            ordered.append(evidence_id)

    for event in perception.events:
        for evidence_id in event.evidence_ids:
            remember(evidence_id)
        if event.conflict_evidence_ids is not None:
            for evidence_id in event.conflict_evidence_ids:
                remember(evidence_id)
    for evidence_id in perception.emotion.evidence_ids:
        remember(evidence_id)
    for observation in perception.image_observations:
        remember(observation.image_evidence_id)
        if observation.related_text_evidence_ids is not None:
            for evidence_id in observation.related_text_evidence_ids:
                remember(evidence_id)
    return tuple(ordered)


def build_attribution_request(
    stage_input: AttributionStageInput, *, prompt: StagePrompt
) -> GlmRequest:
    """构造归因阶段模型请求；获准证据内容缺失时立即失败，不静默省略。

    图片证据的可观察内容已随感知 JSON 的 image_observations 提供（规格 9.2
    允许归因读取图片观察），不在此重发原图或图片内容行。
    """

    cited = cited_ids_in_order(stage_input.perception)
    image_ids = {
        observation.image_evidence_id
        for observation in stage_input.perception.image_observations
    }
    required = [
        evidence_id for evidence_id in cited if evidence_id not in image_ids
    ]
    missing = [
        evidence_id
        for evidence_id in required
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
        "",
        "获准引用的证据内容（只可引用感知结果中出现过的证据编号）：",
    ]
    sections.extend(
        f"[{evidence_id}] {stage_input.evidence_content[evidence_id]}"
        for evidence_id in required
    )
    return GlmRequest(
        stage=AnalysisStage.ATTRIBUTION,
        prompt_version=prompt.version,
        system_prompt=prompt.rendered_text,
        user_content="\n".join(sections),
    )
