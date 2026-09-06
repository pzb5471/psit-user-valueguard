"""M1 共享数据合同：CaseInput v1、三类证据、ZIP manifest 与 checksums（规格第 5.4—5.6 节）。

本文件属于跨模块冻结合同（规格第 3.1 节）：字段名与类型由规格第 5.5、5.6 节
冻结，不由 Task 自行改名；任何取值或字段变化必须作为独立合同变更处理。

共享合同只依赖 Python 标准库、typing 和 Pydantic（规格第 6 节）。
所有模型统一 strict 与 extra="forbid"；可选字段不适用时省略，不用 null、
空数组占位；数组保持输入顺序且 evidence_id 在案例内唯一；金额使用 Decimal
并按十进制定点字符串序列化，禁止二进制浮点（规格第 5.5 节）。

M1-01 不导入 M2 合同；AnalysisRequest 通过 CaseInputV1Protocol（analysis.py）
在 M3 装配期接收本合同的实例。
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    RootModel,
    StringConstraints,
    model_validator,
)

__all__ = [
    "BehaviorEvidence",
    "BehaviorFactType",
    "BatchManifest",
    "CaseInput",
    "ChecksumsFile",
    "Customer",
    "CustomerValue",
    "EvidenceBundle",
    "EvidenceIdentity",
    "EvidenceRole",
    "ImageEvidence",
    "PrimaryOrder",
    "Provenance",
    "SourceRef",
    "TextEvidence",
]

_STRICT = ConfigDict(strict=True, extra="forbid")

_BOUNDED_ID = StringConstraints(min_length=1, max_length=128, pattern=r"^\S(?:.*\S)?$")
_BOUNDED_TEXT = StringConstraints(min_length=1, max_length=512)
_DIALOG_TEXT = StringConstraints(min_length=1, max_length=4096)
_SHA256_HEX = StringConstraints(pattern=r"^[0-9a-f]{64}$")

CaseId = Annotated[str, _BOUNDED_ID]
EvidenceId = Annotated[str, _BOUNDED_ID]
BoundedText = Annotated[str, _BOUNDED_TEXT]
DialogText = Annotated[str, _DIALOG_TEXT]
ContentSha256 = Annotated[str, _SHA256_HEX]


def _require_safe_relative_path(value: str) -> str:
    """ZIP 与来源引用只允许相对路径：禁止绝对路径、盘符、反斜杠与 ..（规格第 5.4 节）。"""

    lowered = value.lower()
    if (
        value.startswith("/")
        or value.startswith("\\")
        or ":" in value
        or "\\" in value
        or lowered.startswith("..")
        or "/../" in lowered
        or lowered.endswith("/..")
    ):
        raise ValueError(f"禁止绝对路径、盘符、反斜杠或路径穿越：{value}")
    return value


RelativePath = Annotated[
    str,
    StringConstraints(min_length=1, max_length=256),
    AfterValidator(_require_safe_relative_path),
]


def _coerce_decimal_amount(value: Any) -> Any:
    """金额必须按十进制定点字符串序列化，禁止二进制浮点（规格第 5.5 节）。"""

    if isinstance(value, float):
        raise ValueError("金额必须使用十进制定点字符串，禁止浮点数")
    if isinstance(value, bool):
        raise ValueError("金额不允许布尔值")
    if isinstance(value, (str, int)):
        try:
            return Decimal(value)
        except InvalidOperation as error:
            raise ValueError(f"非法金额：{value!r}") from error
    return value


DecimalAmount = Annotated[Decimal, BeforeValidator(_coerce_decimal_amount), Field(ge=0)]


class EvidenceIdentity(StrEnum):
    """证据身份（规格第 5.1、5.6 节）：observed、derived、simulated。"""

    OBSERVED = "observed"
    DERIVED = "derived"
    SIMULATED = "simulated"


class EvidenceRole(StrEnum):
    """对话消息角色（规格第 5.6 节）：源数据没有消息时间，不设置 occurred_at。"""

    CUSTOMER = "CUSTOMER"
    SERVICE_AGENT = "SERVICE_AGENT"


class BehaviorFactType(StrEnum):
    """行为事实类型（规格第 5.6 节冻结枚举）。"""

    HIGH_VALUE_CUSTOMER = "HIGH_VALUE_CUSTOMER"
    ORDER_STATUS = "ORDER_STATUS"
    ORDER_PURCHASED_AT = "ORDER_PURCHASED_AT"
    ORDER_APPROVED_AT = "ORDER_APPROVED_AT"
    ORDER_DELIVERED_TO_CARRIER_AT = "ORDER_DELIVERED_TO_CARRIER_AT"
    ORDER_DELIVERED_TO_CUSTOMER_AT = "ORDER_DELIVERED_TO_CUSTOMER_AT"
    ORDER_ESTIMATED_DELIVERY_AT = "ORDER_ESTIMATED_DELIVERY_AT"
    ORDER_PAYMENT_TOTAL = "ORDER_PAYMENT_TOTAL"


class SourceRef(BaseModel):
    """来源引用（规格第 5.5 节）：路径必须相对 source root，不得含绝对路径或 ..。"""

    model_config = _STRICT

    dataset: BoundedText
    relative_path: RelativePath
    record_key: BoundedText
    field: BoundedText | None = None


class _EvidenceBase(BaseModel):
    """三类证据共同字段（规格第 5.6 节）。"""

    model_config = _STRICT

    evidence_id: EvidenceId
    identity: EvidenceIdentity
    relation_identity: Literal["mock_mapped"]
    source_ref: SourceRef
    content_hash: ContentSha256


class TextEvidence(_EvidenceBase):
    """脱敏对话证据（规格第 5.6 节）：源数据没有消息时间，不设置 occurred_at。"""

    sequence_no: int = Field(ge=1)
    role: EvidenceRole
    text: DialogText


class ImageEvidence(_EvidenceBase):
    """图片证据（规格第 5.6 节）：content_hash 即原文件 SHA-256；路径不得越界。"""

    asset_relative_path: RelativePath
    media_type: Literal["image/jpeg", "image/png", "image/gif"]


class BehaviorEvidence(_EvidenceBase):
    """行为事实证据（规格第 5.6 节）：严格标量；派生事实按需附计算规则。

    value 禁止浮点：金额按十进制定点字符串序列化（规格第 5.5 节），
    模型不得修改数值或重算 RFM。
    """

    fact_type: BehaviorFactType
    value: str | int | bool
    calculation_rule: BoundedText | None = None


class EvidenceBundle(BaseModel):
    """案例证据集合（规格第 5.5、5.6 节）。

    图片可以缺失，但案例至少包含一条客户售后消息；evidence_id 在案例内唯一。
    """

    model_config = _STRICT

    text_items: list[TextEvidence] = Field(min_length=1)
    image_items: list[ImageEvidence] = Field(default_factory=list)
    behavior_items: list[BehaviorEvidence] = Field(default_factory=list)

    @model_validator(mode="after")
    def _evidence_bundle_rules(self) -> EvidenceBundle:
        all_items: list[_EvidenceBase] = [
            *self.text_items,
            *self.image_items,
            *self.behavior_items,
        ]
        seen: set[str] = set()
        for item in all_items:
            if item.evidence_id in seen:
                raise ValueError(f"evidence_id 案例内重复：{item.evidence_id}")
            seen.add(item.evidence_id)
        if not any(item.role is EvidenceRole.CUSTOMER for item in self.text_items):
            raise ValueError("案例至少包含一条客户售后消息")
        return self


class PrimaryOrder(BaseModel):
    """主订单（规格第 5.5 节）：仅源数据存在时出现可选履约时间。"""

    model_config = _STRICT

    source_order_id: CaseId
    order_display_id: CaseId
    order_status: BoundedText
    order_purchase_timestamp: AwareDatetime
    payment_total: DecimalAmount
    order_approved_at: AwareDatetime | None = None
    order_delivered_carrier_date: AwareDatetime | None = None
    order_delivered_customer_date: AwareDatetime | None = None
    order_estimated_delivery_date: AwareDatetime | None = None


class Customer(BaseModel):
    """客户（规格第 5.5 节）：不保存城市、州、邮编；源 customer_unique_id 只进 provenance。"""

    model_config = _STRICT

    customer_ref: CaseId


class CustomerValue(BaseModel):
    """高价值结论与复算边界（规格第 5.5 节）：完整内容只供确定性程序复算与追溯。"""

    model_config = _STRICT

    is_high_value: bool
    rule_version: Literal["high_value_rule_v1"]
    snapshot_at: AwareDatetime
    recency_days: int = Field(ge=0)
    frequency_orders: int = Field(ge=1)
    monetary_total: DecimalAmount
    r_p75: DecimalAmount
    m_p80: DecimalAmount
    m_p50: DecimalAmount
    decision_reason: BoundedText
    source_ref: SourceRef


class Provenance(BaseModel):
    """组包追溯（规格第 5.5 节）：无自由说明字段；Mock 关系由可复算清单表达。"""

    model_config = _STRICT

    builder_version: BoundedText
    source_manifest_sha256: ContentSha256
    mapping_manifest_sha256: ContentSha256
    source_refs: list[SourceRef] = Field(min_length=1)


class CaseInput(BaseModel):
    """CaseInput v1（规格第 5.5 节）：顶层字段只允许十个，禁止增加任何其它字段。"""

    model_config = _STRICT

    schema_version: Literal["v1"]
    data_version: Literal["mock_dataset_v1"]
    batch_id: CaseId
    case_id: CaseId
    data_identity: Literal["simulated"]
    primary_order: PrimaryOrder
    customer: Customer
    customer_value: CustomerValue
    evidence: EvidenceBundle
    provenance: Provenance


class BatchManifest(BaseModel):
    """批次 manifest（规格第 5.4 节）：case_files 按路径升序，数量与案例一致。"""

    model_config = _STRICT

    schema_version: Literal["batch_manifest.v1"]
    data_version: Literal["mock_dataset_v1"]
    batch_id: CaseId
    package_type: Literal["DEMO", "ACCEPTANCE"]
    is_mock: Literal[True]
    source_snapshot_at: AwareDatetime
    case_files: list[RelativePath]
    case_count: int = Field(ge=0)
    evidence_count: int = Field(ge=0)

    @model_validator(mode="after")
    def _manifest_rules(self) -> BatchManifest:
        if self.case_files != sorted(self.case_files):
            raise ValueError("case_files 必须按路径升序排列")
        if len(set(self.case_files)) != len(self.case_files):
            raise ValueError("case_files 存在重复路径")
        if self.case_count != len(self.case_files):
            raise ValueError(
                f"case_count {self.case_count} 与 case_files 数量 {len(self.case_files)} 不一致"
            )
        return self


class ChecksumsFile(RootModel[dict[str, ContentSha256]]):
    """checksums.json（规格第 5.4 节）：相对路径 → 小写 SHA-256，不包含自身。"""

    @model_validator(mode="after")
    def _checksum_rules(self) -> ChecksumsFile:
        for path in self.root:
            _require_safe_relative_path(path)
            if path == "checksums.json":
                raise ValueError("checksums.json 不得包含自身")
        return self
