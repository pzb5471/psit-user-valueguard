"""感知阶段输入构造器（M2-05，规格第 9.2 节阶段最小权限）。

只携带当前案例脱敏对话、图片、已核验订单与履约事实、case_id 与可引用
证据编号；不传入高价值结论、RFM、风险答案、动作目录、其他案例或密封答案；
付款金额只供来源追溯，不进入模型上下文（规格第 5.6 节）。
图片由 image_data_resolver 按 asset_relative_path 提供字节（GIF 由装配方
转静态首帧）；无法解析的图片跳过且不进入可引用集合。
"""

from __future__ import annotations

import base64
from collections.abc import Callable

from app.contracts.analysis import AnalysisStage
from app.contracts.data import BehaviorEvidence, BehaviorFactType, CaseInput
from app.modules.analysis.client import GlmRequest, ImageAttachment
from app.modules.analysis.prompts import StagePrompt

__all__ = [
    "ImageResolver",
    "PerceptionStageInput",
    "build_perception_request",
    "citable_evidence_ids",
]

ImageResolver = Callable[[str], tuple[str, bytes]]
"""图片解析器：asset_relative_path → (模型媒体类型, 原始字节)。

GIF 原件由装配方转换为静态首帧并报告 image/png（规格第 5.4 节）；
返回其它媒体类型时该图跳过，不进入请求。
"""

_MODEL_ATTACHMENT_MEDIA = frozenset({"image/jpeg", "image/png"})
_MODEL_EXCLUDED_FACTS = frozenset(
    {BehaviorFactType.ORDER_PAYMENT_TOTAL, BehaviorFactType.HIGH_VALUE_CUSTOMER}
)


class PerceptionStageInput:
    """感知阶段获准输入：CaseInput v1 与图片字节解析器。"""

    __slots__ = ("case_input", "image_data_resolver")

    def __init__(
        self,
        *,
        case_input: CaseInput,
        image_data_resolver: ImageResolver,
    ) -> None:
        self.case_input = case_input
        self.image_data_resolver = image_data_resolver


def _try_resolve_image(
    stage_input: PerceptionStageInput, asset_relative_path: str
) -> tuple[str, bytes] | None:
    try:
        media_type, data = stage_input.image_data_resolver(asset_relative_path)
    except (FileNotFoundError, OSError):
        return None
    if not data or media_type not in _MODEL_ATTACHMENT_MEDIA:
        return None
    return media_type, data


def _attached_images(
    stage_input: PerceptionStageInput,
) -> list[tuple[str, ImageAttachment]]:
    attached: list[tuple[str, ImageAttachment]] = []
    for image in stage_input.case_input.evidence.image_items:
        resolved = _try_resolve_image(stage_input, image.asset_relative_path)
        if resolved is None:
            continue
        media_type, data = resolved
        attached.append(
            (
                image.evidence_id,
                ImageAttachment(
                    media_type=media_type,
                    data_base64=base64.b64encode(data).decode("ascii"),
                ),
            )
        )
    return attached


def citable_evidence_ids(stage_input: PerceptionStageInput) -> frozenset[str]:
    """当前请求实际提供的可引用证据编号：对话、非排除订单事实与已附图片。"""

    ids = {item.evidence_id for item in stage_input.case_input.evidence.text_items}
    ids |= {
        item.evidence_id
        for item in stage_input.case_input.evidence.behavior_items
        if item.fact_type not in _MODEL_EXCLUDED_FACTS
    }
    ids |= {evidence_id for evidence_id, _ in _attached_images(stage_input)}
    return frozenset(ids)


def build_perception_request(
    stage_input: PerceptionStageInput, *, prompt: StagePrompt
) -> GlmRequest:
    """构造感知阶段模型请求；对话按 sequence_no 排序，事实与图片附编号。"""

    case = stage_input.case_input
    sections: list[str] = [
        f"case_id: {case.case_id}",
        "客户与客服对话（脱敏，按时间顺序）：",
    ]
    for item in sorted(case.evidence.text_items, key=lambda text: text.sequence_no):
        sections.append(f"[{item.evidence_id}]（{item.role.value}）{item.text}")

    facts: list[BehaviorEvidence] = [
        item
        for item in case.evidence.behavior_items
        if item.fact_type not in _MODEL_EXCLUDED_FACTS
    ]
    if facts:
        sections.append("已核验的订单与履约事实：")
        sections.extend(
            f"[{item.evidence_id}] {item.fact_type.value}: {item.value}"
            for item in facts
        )

    attached = _attached_images(stage_input)
    if attached:
        sections.append("图片（每张单独提供，编号如下）：")
        sections.extend(
            f"[{evidence_id}]（{attachment.media_type}）"
            for evidence_id, attachment in attached
        )

    return GlmRequest(
        stage=AnalysisStage.PERCEPTION,
        prompt_version=prompt.version,
        system_prompt=prompt.rendered_text,
        user_content="\n".join(sections),
        images=tuple(attachment for _, attachment in attached),
    )
