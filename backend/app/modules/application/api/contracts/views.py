"""业务视图 DTO（技术实施规格 12.2；ADR 0037、0038、0039、0074）。

本模块是 OpenAPI 真源的一部分：字段集合与规格 12.2 白名单逐字对齐，
不返回运行编号、ORM、阶段名、Prompt、Token、模型参数、本机路径、
哈希或原始 JSON。可选字段不适用时省略（路由统一 exclude_none），
不用 null、空数组占位。

枚举直接复用共享合同（states.py、analysis.py）与 M1-05 已冻结的
review_options 措辞（modules/data/queries/views.py，供 M3-03 复审的
显式假设），保证后端同源，不出现第二套取值。
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.contracts.analysis import (
    ActionType,
    AttributionFallbackCause,
    BusinessCause,
    InterventionLevel,
)
from app.contracts.states import BatchStatus, CaseStatus
from app.modules.application.api.contracts.errors import (
    CaseProcessingErrorCode,
    ProcessingErrorStage,
)

__all__ = [
    "ACTION_CATALOG_VERSION",
    "ACTION_TYPE_OPTIONS",
    "ActionView",
    "BatchListView",
    "BatchWorkspaceView",
    "CAUSE_CATEGORY_OPTIONS",
    "CaseDetailView",
    "CaseProcessingErrorView",
    "CaseQueueItemView",
    "CaseQueueView",
    "CauseCategory",
    "CauseView",
    "CitedEvidenceView",
    "EvidenceModality",
    "INTERVENTION_LEVEL_OPTIONS",
    "OptionItem",
    "ReviewOptionsView",
    "ReviewResultView",
    "build_review_options",
]


class _View(BaseModel):
    """视图基类：禁止未声明字段，序列化时省略不适用的可选字段。"""

    model_config = ConfigDict(extra="forbid")


class OptionItem(_View):
    """枚举或动作目录的单档选项（合同 value + 中文 label）。"""

    value: str
    label: str


#: review_options 的动作目录版本。M1-05 已在查询投影中冻结为
#: "action_catalog.v1" 并声明供 M3-03 对齐；API 层同值，不引入第二套版本串。
ACTION_CATALOG_VERSION = "action_catalog.v1"


#: 介入等级三档（规格 7.2；label 与 InterventionLevel.LABELS 同源）。
INTERVENTION_LEVEL_OPTIONS: tuple[OptionItem, ...] = tuple(
    OptionItem(value=value, label=label)
    for value, label in InterventionLevel.LABELS.items()
)

#: 六个业务原因（规格 7.2；措辞与 M1-05 冻结值一致，不含 INSUFFICIENT_EVIDENCE）。
CAUSE_CATEGORY_OPTIONS: tuple[OptionItem, ...] = (
    OptionItem(value="LOGISTICS_FULFILLMENT", label="物流履约问题"),
    OptionItem(value="PRODUCT_ISSUE", label="商品问题"),
    OptionItem(value="RETURN_REFUND", label="退货退款问题"),
    OptionItem(value="SERVICE_COMMUNICATION", label="服务沟通问题"),
    OptionItem(value="PRICE_OR_BENEFIT", label="价格或权益问题"),
    OptionItem(value="OTHER", label="其他"),
)

#: 六项动作（规格 7.3；label 为 config/action_catalog.v1.json 的 description 原文）。
ACTION_TYPE_OPTIONS: tuple[OptionItem, ...] = (
    OptionItem(value="EVIDENCE_CHECK", label="补充或核实图片、物流、订单或退款证据"),
    OptionItem(value="CUSTOMER_CONTACT", label="建议人工联系客户，并给出沟通重点"),
    OptionItem(value="FULFILLMENT_ESCALATION", label="建议升级物流或订单履约处理"),
    OptionItem(value="REPLACEMENT_RETURN_REFUND_CHECK", label="建议补发、退货或退款核验"),
    OptionItem(
        value="APOLOGY_COMPENSATION_RETENTION_REQUEST",
        label="提交但不执行道歉、补偿或挽留申请",
    ),
    OptionItem(value="NO_ACTION_MONITOR", label="暂不采取动作，并说明观察或复查理由"),
)


class ReviewOptionsView(_View):
    """人工确认表单只读选项（规格 12.2；仅 can_review=true 时出现）。"""

    intervention_levels: list[OptionItem]
    cause_categories: list[OptionItem]
    action_catalog_version: str
    action_types: list[OptionItem]


def build_review_options() -> ReviewOptionsView:
    """冻结枚举与动作目录的只读投影；不新增接口，不建立配置管理能力。"""
    return ReviewOptionsView(
        intervention_levels=list(INTERVENTION_LEVEL_OPTIONS),
        cause_categories=list(CAUSE_CATEGORY_OPTIONS),
        action_catalog_version=ACTION_CATALOG_VERSION,
        action_types=list(ACTION_TYPE_OPTIONS),
    )


class BatchWorkspaceView(_View):
    """批次工作台视图（规格 12.2）。"""

    batch_id: str
    source_filename: str
    is_mock: bool
    status: BatchStatus
    case_count: int = Field(ge=0)
    evidence_count: int = Field(ge=0)
    analysis_succeeded_count: int = Field(ge=0)
    error_count: int = Field(ge=0)
    imported_at: datetime
    can_start_analysis: bool
    analysis_unavailable_message: str | None = None


class BatchListView(_View):
    """批次列表（规格 12.2，只含 items 与 total）。"""

    items: list[BatchWorkspaceView]
    total: int = Field(ge=0)


class CaseQueueItemView(_View):
    """案例队列条目（规格 12.2）；三个标记由当前有效结果或运行错误确定。"""

    case_id: str
    customer_display_id: str
    is_high_value: bool
    risk_summary: str | None = None
    intervention_level: InterventionLevel | None = None
    priority_reason: str | None = None
    status: CaseStatus
    has_evidence_conflict: bool
    has_insufficient_evidence: bool
    has_modality_failure: bool


class CaseQueueView(_View):
    """案例队列（规格 12.2，只含 items 与 total）。"""

    items: list[CaseQueueItemView]
    total: int = Field(ge=0)


class CaseProcessingErrorView(_View):
    """仅 status=PROCESSING_ERROR 案例出现的业务化处理异常（规格 12.2/12.4）。"""

    code: CaseProcessingErrorCode
    message: str
    stage: ProcessingErrorStage
    next_action: str
    trace_id: str


class EvidenceModality(StrEnum):
    """cited_evidence 的证据模态（规格 12.2，对应三类证据合同）。"""

    TEXT = "TEXT"
    IMAGE = "IMAGE"
    BEHAVIOR = "BEHAVIOR"


class CitedEvidenceView(_View):
    """当前结果实际引用的业务证据（规格 12.2）。

    图片正文由 M4 用 batch_id、case_id、evidence_id 调用受控证据接口取得，
    不增加 content_url 字段。
    """

    evidence_id: str
    modality: EvidenceModality
    label: str
    text: str | None = None
    summary: str | None = None


#: final_cause / primary_cause 的类别取值：六个业务原因或 INSUFFICIENT_EVIDENCE 兜底。
CauseCategory = BusinessCause | AttributionFallbackCause


class CauseView(_View):
    """风险原因投影（规格 12.2；结构与 M2 归因 Cause 合同对齐）。"""

    category: CauseCategory
    explanation: str
    evidence_ids: list[str] = Field(default_factory=list)
    counter_evidence_ids: list[str] | None = None
    uncertainty: str | None = None


class ActionView(_View):
    """建议动作投影（规格 12.2；action_type 必须来自动作目录）。"""

    action_type: ActionType
    description: str
    reason: str
    evidence_ids: list[str] = Field(default_factory=list)
    precondition: str | None = None


class ReviewResultView(_View):
    """人工确认结果（规格 12.2）。"""

    outcome: str
    final_intervention_level: InterventionLevel | None = None
    final_cause: CauseView | None = None
    final_actions: list[ActionView] | None = None
    execution_note: str | None = None
    review_reason: str | None = None
    created_at: datetime


class CaseDetailView(_View):
    """案例详情（规格 12.2）。"""

    batch_id: str
    case_id: str
    customer_display_id: str
    is_high_value: bool
    customer_value_summary: str
    status: CaseStatus
    intervention_level: InterventionLevel | None = None
    risk_summary: str | None = None
    primary_cause: CauseView | None = None
    actions: list[ActionView] | None = None
    communication_points: list[str] | None = None
    uncertainty: list[str] | None = None
    missing_evidence: list[str] | None = None
    cited_evidence: list[CitedEvidenceView] | None = None
    is_mock: bool
    review_result: ReviewResultView | None = None
    processing_error: CaseProcessingErrorView | None = None
    can_rerun: bool
    can_review: bool
    review_token: str | None = None
    review_options: ReviewOptionsView | None = None
