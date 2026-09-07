"""M2 共享分析合同：三阶段结果、入口请求/结果、事件与动作目录（规格第 5.6、7、9 节）。

本文件属于跨模块冻结合同（规格第 3.1 节）：PerceptionResult、AttributionResult、
DecisionPackage 的字段边界与证据引用规则，AnalysisRequest、AnalysisOutcome、
内部事件、三阶段顺序、一次定向修复与每阶段请求上限都是冻结内容；任何取值或
字段变化必须作为独立合同变更处理，并同步修改合同测试与受影响 Task。

共享合同只依赖 Python 标准库、typing 与 Pydantic（规格第 6 节）。
所有模型统一 strict 与 extra="forbid"，可选字段不适用时省略，不用 null、空数组占位。
字符串默认上限 512、ID 上限 128（规格第 5.6 节 ID 规则）；数组保持输入顺序且
不得含重复 evidence_id。

M2-01 不复制 M1-01 的 CaseInput v1（backend/app/contracts/data.py 属于 M1-01 范围）；
AnalysisRequest 通过 CaseInputV1Protocol 声明最小结构面，由 M3 装配真实 CaseInput 实例。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum, nonmember
from typing import Annotated, Any, Literal, Protocol, runtime_checkable

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

__all__ = [
    "ACTION_CATALOG_VERSION",
    "ActionType",
    "AnalysisCompletedEvent",
    "AnalysisErrorCode",
    "AnalysisEvent",
    "AnalysisEventSink",
    "AnalysisOutcome",
    "AnalysisRequest",
    "AnalysisStage",
    "AnalysisFailure",
    "AnalysisSuccess",
    "AttributionFallbackCause",
    "AttributionResult",
    "BusinessCause",
    "CaseInputV1Protocol",
    "Cause",
    "ContractVersion",
    "DecisionPackage",
    "Emotion",
    "EmotionAssessment",
    "ImageAnalysisStatus",
    "ImageObservation",
    "ImageTextRelation",
    "InterventionLevel",
    "ModelAttemptFinishedEvent",
    "PerceptionEventItem",
    "PerceptionResult",
    "ResolutionStatus",
    "StageFailedEvent",
    "StageResultValidatedEvent",
    "StageStartedEvent",
    "StatementBasis",
    "StrategyAction",
    "TraceId",
    "UTCDateTime",
]

ACTION_CATALOG_VERSION = "v1"

_STRICT = ConfigDict(strict=True, extra="forbid")

_BOUNDED_ID = StringConstraints(min_length=1, max_length=128, pattern=r"^\S(?:.*\S)?$")
_BOUNDED_TEXT = StringConstraints(min_length=1, max_length=512)

CaseId = Annotated[str, _BOUNDED_ID]
EvidenceId = Annotated[str, _BOUNDED_ID]
BoundedText = Annotated[str, _BOUNDED_TEXT]


def _reject_duplicate_evidence_ids(values: list[EvidenceId]) -> list[EvidenceId]:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            raise ValueError(f"evidence_id 重复：{value}")
        seen.add(value)
    return values


EvidenceIdList = Annotated[list[EvidenceId], AfterValidator(_reject_duplicate_evidence_ids)]


class InterventionLevel(StrEnum):
    """系统建议介入等级；等级语义与程序底线见规格第 7.4 节。"""

    MUST_INTERVENE = "MUST_INTERVENE"
    SHOULD_INTERVENE = "SHOULD_INTERVENE"
    NO_IMMEDIATE_INTERVENTION = "NO_IMMEDIATE_INTERVENTION"

    LABELS = nonmember(
        {
            "MUST_INTERVENE": "必须介入",
            "SHOULD_INTERVENE": "建议介入",
            "NO_IMMEDIATE_INTERVENTION": "暂不介入",
        }
    )

    ORDER = nonmember(
        {
            "MUST_INTERVENE": 1,
            "SHOULD_INTERVENE": 2,
            "NO_IMMEDIATE_INTERVENTION": 3,
        }
    )


class BusinessCause(StrEnum):
    """六个业务原因类别。"""

    LOGISTICS_FULFILLMENT = "LOGISTICS_FULFILLMENT"
    PRODUCT_ISSUE = "PRODUCT_ISSUE"
    RETURN_REFUND = "RETURN_REFUND"
    SERVICE_COMMUNICATION = "SERVICE_COMMUNICATION"
    PRICE_OR_BENEFIT = "PRICE_OR_BENEFIT"
    OTHER = "OTHER"


class AttributionFallbackCause(StrEnum):
    """归因无法可靠判断时的非原因兜底值。"""

    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class StatementBasis(StrEnum):
    """事件陈述状态（规格第 7.1 节）：区分客户声称、客服陈述或承诺、客户确认结果、
    图片直接观察和程序派生事实。"""

    CUSTOMER_CLAIMED = "CUSTOMER_CLAIMED"
    SERVICE_AGENT_STATED_OR_PROMISED = "SERVICE_AGENT_STATED_OR_PROMISED"
    CUSTOMER_CONFIRMED = "CUSTOMER_CONFIRMED"
    IMAGE_DIRECT_OBSERVATION = "IMAGE_DIRECT_OBSERVATION"
    PROGRAM_DERIVED = "PROGRAM_DERIVED"


class ResolutionStatus(StrEnum):
    """事件解决状态（规格第 7.1 节）：只允许已解决、未解决、无法确认。"""

    RESOLVED = "RESOLVED"
    UNRESOLVED = "UNRESOLVED"
    UNCONFIRMABLE = "UNCONFIRMABLE"


class ImageAnalysisStatus(StrEnum):
    """图片分析状态：图片可观察时为 ANALYZED；无法判断图片内容时为 UNKNOWN。"""

    ANALYZED = "ANALYZED"
    UNKNOWN = "UNKNOWN"


class ImageTextRelation(StrEnum):
    """图片与客户陈述的关系（规格第 7.1 节）：相互支持、相互冲突、补充信息、无法判断。"""

    MUTUALLY_SUPPORTS = "MUTUALLY_SUPPORTS"
    CONFLICTS_WITH = "CONFLICTS_WITH"
    SUPPLEMENTS = "SUPPLEMENTS"
    UNDETERMINED = "UNDETERMINED"


class Emotion(StrEnum):
    """客户情绪（规格第 7.1 节）：只允许平静、不耐烦、无法判断，不得依据客服语气推断。"""

    CALM = "CALM"
    IMPATIENT = "IMPATIENT"
    UNDETERMINED = "UNDETERMINED"


class ActionType(StrEnum):
    """动作目录 v1 的六个动作代码（规格第 7.3 节），与 config/action_catalog.v1.json 一一对应。"""

    EVIDENCE_CHECK = "EVIDENCE_CHECK"
    CUSTOMER_CONTACT = "CUSTOMER_CONTACT"
    FULFILLMENT_ESCALATION = "FULFILLMENT_ESCALATION"
    REPLACEMENT_RETURN_REFUND_CHECK = "REPLACEMENT_RETURN_REFUND_CHECK"
    APOLOGY_COMPENSATION_RETENTION_REQUEST = "APOLOGY_COMPENSATION_RETENTION_REQUEST"
    NO_ACTION_MONITOR = "NO_ACTION_MONITOR"


class PerceptionEventItem(BaseModel):
    """单条感知事件（规格第 7.1 节）：编号、类别、摘要、陈述状态、解决状态与支持证据。

    类别取值由 Prompt 约束为受控词表，程序不在合同层冻结其值域；
    每条事件至少引用一条当前案例证据。
    """

    model_config = _STRICT

    event_no: int = Field(ge=1)
    category: BoundedText
    summary: BoundedText
    statement_basis: StatementBasis
    resolution: ResolutionStatus
    evidence_ids: EvidenceIdList = Field(min_length=1)
    conflict_evidence_ids: EvidenceIdList | None = None
    uncertainty: BoundedText | None = None


class ImageObservation(BaseModel):
    """单张输入图片的观察（规格第 7.1 节）：每张输入图片对应一条，只保存图片证据编号、
    分析状态、最多三条可观察事实、与客户陈述的关系、关联文本证据和按需不确定性。

    禁止检测框、坐标、概率、Embedding 或特征向量；UNKNOWN 图片不得输出
    可观察事实（不得从文本反推图片内容）。
    """

    model_config = _STRICT

    image_evidence_id: EvidenceId
    analysis_status: ImageAnalysisStatus
    observable_facts: list[BoundedText] = Field(default_factory=list, max_length=3)
    relation: ImageTextRelation
    related_text_evidence_ids: EvidenceIdList | None = None
    uncertainty: BoundedText | None = None

    @model_validator(mode="after")
    def _unknown_image_has_no_invented_facts(self) -> ImageObservation:
        if self.analysis_status is ImageAnalysisStatus.UNKNOWN and self.observable_facts:
            raise ValueError("UNKNOWN 图片不得输出可观察事实（不得从文本反推图片内容）")
        return self


class EmotionAssessment(BaseModel):
    """客户情绪判断（规格第 7.1 节）：必须引用客户文本证据。"""

    model_config = _STRICT

    value: Emotion
    evidence_ids: EvidenceIdList = Field(min_length=1)


class PerceptionResult(BaseModel):
    """感知阶段结果（规格第 7.1 节）：顶层只允许六个字段。"""

    model_config = _STRICT

    schema_version: Literal["v1"]
    case_id: CaseId
    events: list[PerceptionEventItem]
    image_observations: list[ImageObservation] = Field(default_factory=list)
    emotion: EmotionAssessment
    missing_evidence: list[BoundedText] = Field(default_factory=list)


class Cause(BaseModel):
    """风险原因（规格第 7.1 节）：受控类别为六个业务原因或 INSUFFICIENT_EVIDENCE 兜底，
    不得并入 OTHER，也不得表述为已证明的因果事实。"""

    model_config = _STRICT

    category: BusinessCause | AttributionFallbackCause
    explanation: BoundedText
    evidence_ids: EvidenceIdList = Field(default_factory=list)
    counter_evidence_ids: EvidenceIdList | None = None
    uncertainty: BoundedText | None = None


class AttributionResult(BaseModel):
    """归因阶段结果（规格第 7.1 节）：顶层只允许五个字段，备选原因最多一个。"""

    model_config = _STRICT

    schema_version: Literal["v1"]
    case_id: CaseId
    risk_summary: BoundedText
    primary_cause: Cause
    alternative_cause: Cause | None = None


class StrategyAction(BaseModel):
    """建议动作（规格第 7.3 节）：类型必须来自动作目录；不得生成具体补偿金额、
    权益承诺、退款完成状态或真实执行结果；requires_human_approval 由产品门禁执行，
    不由模型输出。"""

    model_config = _STRICT

    action_type: ActionType
    description: BoundedText
    reason: BoundedText
    evidence_ids: EvidenceIdList = Field(default_factory=list)
    precondition: BoundedText | None = None


class DecisionPackage(BaseModel):
    """策略阶段结果（规格第 7.1 节）：动作最多三项、沟通重点最多三项；
    最低介入底线由程序执行（规格第 7.4 节），不在本合同内复算。"""

    model_config = _STRICT

    schema_version: Literal["v1"]
    case_id: CaseId
    intervention_level: InterventionLevel
    priority_reason: BoundedText
    actions: list[StrategyAction] = Field(min_length=1, max_length=3)
    communication_points: list[BoundedText] = Field(default_factory=list, max_length=3)
    caution_note: BoundedText | None = None


TraceId = Annotated[str, _BOUNDED_ID]
ContractVersion = Annotated[str, _BOUNDED_ID]


@runtime_checkable
class CaseInputV1Protocol(Protocol):
    """CaseInput v1 的最小结构面（字段合同由 M1-01 在 backend/app/contracts/data.py 冻结）。

    M2-01 不复制数据合同；M3 装配 AnalysisEngine 时传入真实 CaseInput 实例。
    Pydantic 以 isinstance 校验该结构面，真实 Pydantic 模型天然满足。
    """

    case_id: str


class AnalysisStage(StrEnum):
    """三个顺序分析阶段（规格第 9.1、9.3 节）：同一案例严格按感知、归因、策略执行。"""

    PERCEPTION = "PERCEPTION"
    ATTRIBUTION = "ATTRIBUTION"
    STRATEGY = "STRATEGY"


class AnalysisErrorCode(StrEnum):
    """失败的稳定错误分类（规格第 9.1 节），取值映射规格第 9.3 节重试边界。

    MODEL_TIMEOUT、MODEL_NETWORK、MODEL_RATE_LIMITED、MODEL_PROVIDER_ERROR
    属可重试供应商错误；MODEL_AUTH_REJECTED、MODEL_REQUEST_INVALID、
    MODEL_OUTPUT_INVALID、INPUT_CONTRACT_INVALID 不重试；EVENT_SINK_FAILED
    表示事件持久化失败，必须立即停止当前案例；APP_INTERRUPTED 表示正常关闭
    已完成当前请求及记录，但不再开始下一阶段。
    """

    MODEL_TIMEOUT = "MODEL_TIMEOUT"
    MODEL_NETWORK = "MODEL_NETWORK"
    MODEL_RATE_LIMITED = "MODEL_RATE_LIMITED"
    MODEL_PROVIDER_ERROR = "MODEL_PROVIDER_ERROR"
    MODEL_AUTH_REJECTED = "MODEL_AUTH_REJECTED"
    MODEL_REQUEST_INVALID = "MODEL_REQUEST_INVALID"
    MODEL_OUTPUT_INVALID = "MODEL_OUTPUT_INVALID"
    INPUT_CONTRACT_INVALID = "INPUT_CONTRACT_INVALID"
    EVENT_SINK_FAILED = "EVENT_SINK_FAILED"
    APP_INTERRUPTED = "APP_INTERRUPTED"


class AnalysisRequest(BaseModel):
    """M2 唯一入口的请求（规格第 9.1 节）：只组合 trace_id、内部 case_run_id、
    CaseInput v1、三份结果合同版本、三阶段 Prompt 版本与动作目录版本。

    M2 不得依据数据库、其他案例、密封答案或页面状态补充上下文；
    case_run_id 对应 case_runs 内部整数主键（规格第 11.1 节），不对外暴露。
    """

    model_config = ConfigDict(strict=True, extra="forbid", arbitrary_types_allowed=True)

    trace_id: TraceId
    case_run_id: int = Field(ge=1)
    case_input: CaseInputV1Protocol
    perception_contract_version: ContractVersion
    attribution_contract_version: ContractVersion
    strategy_contract_version: ContractVersion
    perception_prompt_version: ContractVersion
    attribution_prompt_version: ContractVersion
    strategy_prompt_version: ContractVersion
    action_catalog_version: ContractVersion


class AnalysisSuccess(BaseModel):
    """成功结果（规格第 9.1 节）：同一 case_id 的三份阶段结果。

    证据不足只要结果结构完整即属于成功，进入 PENDING_REVIEW，不属于技术失败。
    """

    model_config = _STRICT

    status: Literal["SUCCESS"]
    perception: PerceptionResult
    attribution: AttributionResult
    decision: DecisionPackage

    @model_validator(mode="after")
    def _results_share_one_case_id(self) -> AnalysisSuccess:
        case_ids = {self.perception.case_id, self.attribution.case_id, self.decision.case_id}
        if len(case_ids) != 1:
            raise ValueError("三份阶段结果必须属于同一 case_id")
        return self


class AnalysisFailure(BaseModel):
    """失败结果（规格第 9.1 节）：稳定错误分类、失败阶段、是否耗尽允许尝试与 trace_id。"""

    model_config = _STRICT

    status: Literal["FAILED"]
    error_code: AnalysisErrorCode
    error_stage: AnalysisStage
    attempts_exhausted: bool
    trace_id: TraceId


AnalysisOutcome = Annotated[AnalysisSuccess | AnalysisFailure, Field(discriminator="status")]


def _require_timezone_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("程序时间必须带时区（毫秒 UTC ISO 8601，规格第 11.2 节）")
    if value.utcoffset() != timedelta(0):
        raise ValueError("程序时间必须使用 UTC 时区（规格第 11.2 节）")
    return value


UTCDateTime = Annotated[datetime, AfterValidator(_require_timezone_aware)]


class StageStartedEvent(BaseModel):
    """阶段开始事件：引擎在进入每个阶段前依次发出（规格第 9.1 节）。"""

    model_config = _STRICT

    event_type: Literal["STAGE_STARTED"]
    stage: AnalysisStage
    started_at: UTCDateTime


class ModelAttemptFinishedEvent(BaseModel):
    """模型尝试结束事件（规格第 9.1、9.3 节）：每次调用保存模型名、Prompt 版本、
    请求清单、尝试序号、状态、响应或错误、开始结束时间、耗时和供应商实际返回的
    可用 Token 计数。

    request_manifest 的字段结构由 M2-03 的 GlmClient 产出并冻结，事件原样转发；
    status=SUCCEEDED 时携带 response_json，status=FAILED 时携带 error_code 与
    error_summary，不适用字段省略。
    """

    model_config = _STRICT

    event_type: Literal["MODEL_ATTEMPT_FINISHED"]
    stage: AnalysisStage
    attempt_no: int = Field(ge=1)
    model_name: BoundedText
    prompt_version: ContractVersion
    status: Literal["SUCCEEDED", "FAILED"]
    started_at: UTCDateTime
    finished_at: UTCDateTime
    latency_ms: int | None = Field(default=None, ge=0)
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    request_manifest: dict[str, Any]
    response_json: dict[str, Any] | None = None
    error_code: AnalysisErrorCode | None = None
    error_summary: BoundedText | None = None

    @model_validator(mode="after")
    def _fields_match_status_and_time(self) -> ModelAttemptFinishedEvent:
        if self.finished_at < self.started_at:
            raise ValueError("模型尝试结束时间不得早于开始时间")
        if self.status == "SUCCEEDED":
            if self.response_json is None:
                raise ValueError("成功尝试必须携带 response_json")
            if self.error_code is not None or self.error_summary is not None:
                raise ValueError("成功尝试不得携带错误字段")
        elif (
            self.response_json is not None
            or self.error_code is None
            or self.error_summary is None
        ):
            raise ValueError("失败尝试必须只携带 error_code 与 error_summary")
        return self


class StageResultValidatedEvent(BaseModel):
    """阶段结果校验通过事件：携带通过严格校验的结果，供 M3 保存到 stage_results。"""

    model_config = _STRICT

    event_type: Literal["STAGE_RESULT_VALIDATED"]
    stage: AnalysisStage
    contract_version: ContractVersion
    result: PerceptionResult | AttributionResult | DecisionPackage

    @model_validator(mode="after")
    def _result_matches_stage(self) -> StageResultValidatedEvent:
        expected_type = {
            AnalysisStage.PERCEPTION: PerceptionResult,
            AnalysisStage.ATTRIBUTION: AttributionResult,
            AnalysisStage.STRATEGY: DecisionPackage,
        }[self.stage]
        if not isinstance(self.result, expected_type):
            raise ValueError("阶段名称必须与结果合同类型一致")
        return self


class StageFailedEvent(BaseModel):
    """阶段失败事件：阶段失败后停止后续阶段（规格第 9.3 节），不影响同批其他案例。"""

    model_config = _STRICT

    event_type: Literal["STAGE_FAILED"]
    stage: AnalysisStage
    error_code: AnalysisErrorCode
    error_detail: BoundedText | None = None


class AnalysisCompletedEvent(BaseModel):
    """案例分析结束事件：成功事件不得携带错误字段，失败事件必须携带错误字段。"""

    model_config = _STRICT

    event_type: Literal["ANALYSIS_COMPLETED"]
    status: Literal["SUCCESS", "FAILED"]
    finished_at: UTCDateTime
    error_stage: AnalysisStage | None = None
    error_code: AnalysisErrorCode | None = None

    @model_validator(mode="after")
    def _error_fields_match_status(self) -> AnalysisCompletedEvent:
        has_error = self.error_stage is not None or self.error_code is not None
        if self.status == "SUCCESS" and has_error:
            raise ValueError("成功事件不得携带错误字段")
        if self.status == "FAILED" and (self.error_stage is None or self.error_code is None):
            raise ValueError("失败事件必须携带 error_stage 与 error_code")
        return self


AnalysisEvent = Annotated[
    StageStartedEvent
    | ModelAttemptFinishedEvent
    | StageResultValidatedEvent
    | StageFailedEvent
    | AnalysisCompletedEvent,
    Field(discriminator="event_type"),
]


@runtime_checkable
class AnalysisEventSink(Protocol):
    """事件出口（规格第 9.1 节）：同步依次接收五类事件，由 M3 提供实现并调用 M1
    保存运行记录。

    事件持久化失败时出口实现可以抛出异常，引擎必须立即停止当前案例，
    不能继续运行后假装记录完整；M2 对出口内部实现不做任何假设。
    """

    def emit(self, event: AnalysisEvent) -> None: ...
