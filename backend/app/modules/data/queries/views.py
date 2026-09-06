"""M1-05：CaseQueryGateway 业务投影 DTO（技术实施规格 8/10.3/12.1/12.2）。

本模块冻结查询网关返回的、可直接映射业务 DTO 的投影对象：

- 只包含规格 12.2 白名单字段，不返回 ORM、内部整数主键、run_id、
  data_version/schema_version、阶段名、Prompt、Token、路径、哈希或原始 JSON；
- 所有模型使用 Pydantic 严格模式与 extra="forbid"，不做宽松类型转换；
- review_options 是后端冻结枚举与动作目录的只读投影（规格 7.2/7.3；
  人工表单选项不新增接口，仅在后端同源返回），action_catalog_version
  固定为 action_catalog.v1，不含 INSUFFICIENT_EVIDENCE。

显式假设（超出规格字面处在此声明，供 M2-01/M3-03 与人工 PR 复审）：
- is_mock 从案例数据身份 data_identity=="simulated" 推导，当前 v1 恒为 True；
- actions/communication_points/primary_cause/uncertainty/missing_evidence
  投影当前 case_run 的 stage_result 合同结构（键名由 M2-01 冻结后对齐）。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

ACTION_CATALOG_VERSION = "action_catalog.v1"

#: 业务化处理异常阶段白名单（规格 12.2/12.4），不暴露内部阶段名。
ProcessingErrorStage = Literal[
    "INPUT_PREPARATION",
    "EVIDENCE_PROCESSING",
    "AI_ANALYSIS",
    "RESULT_PERSISTENCE",
    "APP_RECOVERY",
]


class _View(BaseModel):
    """查询投影基类：严格模式 + 禁止额外字段（规格 12.2）。"""

    model_config = ConfigDict(strict=True, extra="forbid")


class OptionItem(_View):
    """枚举或动作目录的单档选项（合同 value + 中文 label）。"""

    value: str
    label: str


class ReviewOptionsView(_View):
    """人工确认表单只读选项（规格 12.2/7.2/7.3；仅 can_review=true 时返回）。"""

    intervention_levels: list[OptionItem]
    cause_categories: list[OptionItem]
    action_catalog_version: str
    action_types: list[OptionItem]


INTERVENTION_LEVEL_OPTIONS: tuple[OptionItem, ...] = (
    OptionItem(value="MUST_INTERVENE", label="必须介入"),
    OptionItem(value="SHOULD_INTERVENE", label="建议介入"),
    OptionItem(value="NO_IMMEDIATE_INTERVENTION", label="暂不介入"),
)

CAUSE_CATEGORY_OPTIONS: tuple[OptionItem, ...] = (
    OptionItem(value="LOGISTICS_FULFILLMENT", label="物流履约问题"),
    OptionItem(value="PRODUCT_ISSUE", label="商品问题"),
    OptionItem(value="RETURN_REFUND", label="退货退款问题"),
    OptionItem(value="SERVICE_COMMUNICATION", label="服务沟通问题"),
    OptionItem(value="PRICE_OR_BENEFIT", label="价格或权益问题"),
    OptionItem(value="OTHER", label="其他"),
)

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


def build_review_options() -> ReviewOptionsView:
    """冻结枚举与动作目录的只读投影（规格 7.2/7.3；不含 INSUFFICIENT_EVIDENCE）。"""
    return ReviewOptionsView(
        intervention_levels=list(INTERVENTION_LEVEL_OPTIONS),
        cause_categories=list(CAUSE_CATEGORY_OPTIONS),
        action_catalog_version=ACTION_CATALOG_VERSION,
        action_types=list(ACTION_TYPE_OPTIONS),
    )


class BatchWorkspaceView(_View):
    """批次投影（规格 12.2 BatchWorkspaceView）。"""

    batch_id: str
    source_filename: str
    is_mock: bool
    status: str
    case_count: int
    evidence_count: int
    analysis_succeeded_count: int
    error_count: int
    imported_at: str
    can_start_analysis: bool
    analysis_unavailable_message: str | None = None


class BatchListView(_View):
    """批次列表（规格 12.2 BatchListView，只含 items 与 total）。"""

    items: list[BatchWorkspaceView]
    total: int


class CaseQueueItemView(_View):
    """案例队列条目（规格 12.2 CaseQueueItemView）。"""

    case_id: str
    customer_display_id: str
    is_high_value: bool
    risk_summary: str | None = None
    intervention_level: str | None = None
    priority_reason: str | None = None
    status: str
    has_evidence_conflict: bool
    has_insufficient_evidence: bool
    has_modality_failure: bool


class CaseQueueView(_View):
    """案例队列（规格 12.2 CaseQueueView，只含 items 与 total）。"""

    items: list[CaseQueueItemView]
    total: int


class CaseProcessingErrorView(_View):
    """仅 PROCESSING_ERROR 案例出现的业务化处理异常（规格 12.2/12.4）。

    stage 只允许五个业务阶段值，不把感知/归因/策略等内部阶段透传给运营人员。
    """

    code: str
    message: str
    stage: ProcessingErrorStage
    next_action: str
    trace_id: str


class CitedEvidenceView(_View):
    """当前结果实际引用的业务证据（规格 12.2 cited_evidence）。

    只返回 evidence_id、modality、业务 label 与按证据类型出现的脱敏文本或
    可显示摘要；不返回本机路径、哈希、内部数据身份或来源 JSON。
    """

    evidence_id: str
    modality: str
    label: str
    text: str | None = None
    summary: str | None = None


class ReviewResultView(_View):
    """人工确认结果（规格 12.2 ReviewResultView）。

    系统原结果通过 reviews.case_run_id 引用不可变 stage_results，不在本视图
    复制第二份决策包（规格第 8 节）。
    """

    outcome: str
    final_intervention_level: str | None = None
    final_cause: dict[str, Any] | None = None
    final_actions: list[Any] | None = None
    execution_note: str | None = None
    review_reason: str | None = None
    created_at: str


class CaseDetailView(_View):
    """案例详情（规格 12.2 CaseDetailView）。"""

    batch_id: str
    case_id: str
    customer_display_id: str
    is_high_value: bool
    customer_value_summary: str
    status: str
    intervention_level: str | None = None
    risk_summary: str | None = None
    primary_cause: dict[str, Any] | None = None
    actions: list[Any] | None = None
    communication_points: list[Any] | None = None
    uncertainty: list[Any] | None = None
    missing_evidence: list[Any] | None = None
    cited_evidence: list[CitedEvidenceView] | None = None
    is_mock: bool
    review_result: ReviewResultView | None = None
    processing_error: CaseProcessingErrorView | None = None
    can_rerun: bool
    can_review: bool
    review_token: str | None = None
    review_options: ReviewOptionsView | None = None


__all__ = [
    "ACTION_CATALOG_VERSION",
    "ACTION_TYPE_OPTIONS",
    "BatchListView",
    "BatchWorkspaceView",
    "CAUSE_CATEGORY_OPTIONS",
    "CaseDetailView",
    "CaseProcessingErrorView",
    "CaseQueueItemView",
    "CaseQueueView",
    "CitedEvidenceView",
    "INTERVENTION_LEVEL_OPTIONS",
    "OptionItem",
    "ProcessingErrorStage",
    "ReviewOptionsView",
    "ReviewResultView",
    "build_review_options",
]
