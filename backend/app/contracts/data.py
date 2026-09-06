"""数据共享合同：CaseInput v1、三类证据、ZIP manifest 与 checksums（技术实施规格第 5.4—5.6 节）。

本模块只允许依赖 Python 标准库、typing 与 Pydantic（规格第 6 节）；不得导入
FastAPI、SQLAlchemy、Alembic、智谱 SDK 或任何模块实现。所有模型统一使用 Pydantic
严格模式与 extra="forbid"，不在字符串、数字、布尔值、对象和数组之间做宽松转换。

冻结内容与显式假设（超出规格字面处在此声明，供 M2/M3 与后续 M1 卡人工复核）：
- CaseInput v1 顶层只允许 10 个字段（规格 5.5；ADR-0018），data_identity 在当前
  mock_dataset_v1 固定为 Literal["simulated"]。
- 规格只冻结 manifest 的字面量 schema_version="batch_manifest.v1"；CaseInput 的
  schema_version 未给字面量，本 v1 按 ADR-0018 的 "CaseInput v1" 表述假定为
  "case_input.v1"，见 CASE_INPUT_SCHEMA_VERSION。
- data_version 为非空可打印文本；mock_dataset_v1 是当前固定数据版本（规格 5.4），
  数据或映射变化时允许产生新 data_version，因此不冻结为字面量。
- 金额统一为 Decimal（规格 5.5：金额使用 Python Decimal 计算并按十进制定点字符串
  序列化）。JSON 交换中金额是十进制定点字符串，因此 Amount 接受 Decimal 或等价
  十进制定点字符串，拒绝 float/int/bool 等宽松输入，避免二进制浮点累计误差。
- 时间同样以 ISO 8601 字符串交换（规格 5.5），Timestamp 接受 datetime 或 ISO 8601
  字符串，拒绝数字等宽松输入。枚举字段接受枚举成员或其在 JSON 中的精确字符串值，
  其余字符串与数值一律拒绝。除此之外的标量保持 Pydantic 严格模式（"1" 不等于 1、
  "true" 不等于 true）。
- relation_identity 在当前固定组合中固定为 mock_mapped（规格 5.6）；fact_type 只允许
  规格列出的 8 个；evidence 三个数组固定存在，图片可缺失（空数组表示无图片），
  但案例至少包含一条有效脱敏客户售后消息。

导入结果（导入摘要/逐项拒绝）与 M1 的五组公开 Protocol 属于 M1-04~M1-08 的模块边界
（规格第 8 节；模块接口合同 §2 注释），不在本文件提前冻结。
"""

import re
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    RootModel,
    model_validator,
)

CASE_INPUT_SCHEMA_VERSION = "case_input.v1"
BATCH_MANIFEST_SCHEMA_VERSION = "batch_manifest.v1"
HIGH_VALUE_RULE_VERSION = "high_value_rule_v1"
MOCK_DATA_VERSION = "mock_dataset_v1"

_MAX_ID_LENGTH = 128
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_DRIVE_LETTER_PATTERN = re.compile(r"^[A-Za-z]:")


def _validate_printable_text(value: str) -> str:
    """ID 类文本：1—128 个可打印且非空字符（规格 5.6 统一 ID 规则）。"""
    if not (1 <= len(value) <= _MAX_ID_LENGTH) or not value.isprintable():
        raise ValueError("文本必须为 1-128 个可打印字符且不能为空")
    return value


def _validate_sha256(value: str) -> str:
    """SHA-256：64 位小写十六进制（规格 5.4/5.6）。"""
    if not _SHA256_PATTERN.fullmatch(value):
        raise ValueError("SHA-256 必须为 64 位小写十六进制")
    return value


def _validate_relative_path(value: str) -> str:
    """相对路径：相对 source root，不得为绝对路径或包含 '..' 段（规格 5.5/5.6）。"""
    if not value or value.startswith(("/", "\\")):
        raise ValueError("路径必须为相对路径且不能为空")
    if _DRIVE_LETTER_PATTERN.match(value) or "\\" in value:
        raise ValueError("路径不得为绝对路径且仅允许使用 '/' 分隔符")
    if any(segment == ".." for segment in value.split("/")):
        raise ValueError("路径不得包含 '..' 段")
    return value


def _validate_case_file_path(value: str) -> str:
    """manifest.case_files：必须是 cases/ 下的 JSON 文件相对路径（规格 5.4）。"""
    if not value.startswith("cases/") or not value.endswith(".json"):
        raise ValueError("案例文件路径必须形如 cases/<名称>.json")
    return value


def _parse_decimal(value: object) -> Decimal:
    """金额：Decimal 直通，十进制定点字符串精确转换（规格 5.5）；拒绝其他类型。"""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, str):
        try:
            return Decimal(value)
        except InvalidOperation as exc:
            raise ValueError("金额必须为十进制定点字符串，例如 '918.16'") from exc
    raise ValueError("金额必须为 Decimal 或十进制定点字符串")


def _parse_datetime(value: object) -> datetime:
    """时间：datetime 直通，ISO 8601 字符串精确转换（规格 5.5）；拒绝其他类型。"""
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("时间必须为 ISO 8601 字符串，例如 '2018-03-12T09:24:00'") from exc
    raise ValueError("时间必须为 datetime 或 ISO 8601 字符串")


def _enum_parser(enum_type: type[StrEnum]) -> Callable[[object], object]:
    """枚举：成员直通，其精确字符串值按成员解析；其余输入拒绝（规格 5.6）。"""

    def parse(value: object) -> object:
        if isinstance(value, enum_type):
            return value
        if isinstance(value, str):
            return enum_type(value)
        raise ValueError(f"{enum_type.__name__} 必须为枚举成员或其字符串值")

    return parse


Amount = Annotated[Decimal, BeforeValidator(_parse_decimal)]
Timestamp = Annotated[datetime, BeforeValidator(_parse_datetime)]
PrintableText = Annotated[str, AfterValidator(_validate_printable_text)]
Sha256Hex = Annotated[str, AfterValidator(_validate_sha256)]
RelativePath = Annotated[str, AfterValidator(_validate_relative_path)]
CaseFilePath = Annotated[
    str,
    AfterValidator(_validate_relative_path),
    AfterValidator(_validate_case_file_path),
]


class EvidenceIdentity(StrEnum):
    """证据数据身份（规格 5.6）：observed / derived / simulated。"""

    OBSERVED = "observed"
    DERIVED = "derived"
    SIMULATED = "simulated"


class RelationIdentity(StrEnum):
    """证据关系身份（规格 5.6）：当前固定组合为 mock_mapped。"""

    MOCK_MAPPED = "mock_mapped"


class TextRole(StrEnum):
    """售后消息角色（规格 5.6）。"""

    CUSTOMER = "CUSTOMER"
    SERVICE_AGENT = "SERVICE_AGENT"


class ImageMediaType(StrEnum):
    """售后图片媒体类型（规格 5.4/5.6）：只接受 JPG/JPEG、PNG、GIF。"""

    JPEG = "image/jpeg"
    PNG = "image/png"
    GIF = "image/gif"


class BehaviorFactType(StrEnum):
    """行为证据事实类型（规格 5.6），只允许下列 8 个。"""

    HIGH_VALUE_CUSTOMER = "HIGH_VALUE_CUSTOMER"
    ORDER_STATUS = "ORDER_STATUS"
    ORDER_PURCHASED_AT = "ORDER_PURCHASED_AT"
    ORDER_APPROVED_AT = "ORDER_APPROVED_AT"
    ORDER_DELIVERED_TO_CARRIER_AT = "ORDER_DELIVERED_TO_CARRIER_AT"
    ORDER_DELIVERED_TO_CUSTOMER_AT = "ORDER_DELIVERED_TO_CUSTOMER_AT"
    ORDER_ESTIMATED_DELIVERY_AT = "ORDER_ESTIMATED_DELIVERY_AT"
    ORDER_PAYMENT_TOTAL = "ORDER_PAYMENT_TOTAL"


class PackageType(StrEnum):
    """标准 ZIP 包类型（规格 5.4）：DEMO 或 ACCEPTANCE。"""

    DEMO = "DEMO"
    ACCEPTANCE = "ACCEPTANCE"


class _StrictModel(BaseModel):
    """共享合同统一基类：严格类型校验、禁止未声明字段（模块接口合同 §2）。"""

    model_config = ConfigDict(strict=True, extra="forbid")


class SourceRef(_StrictModel):
    """来源引用（规格 5.5）：路径相对 source root，不得含绝对路径或 '..'。"""

    dataset: PrintableText
    relative_path: RelativePath
    record_key: PrintableText
    field: PrintableText | None = None


class _EvidenceBase(_StrictModel):
    """三类证据共同字段（规格 5.6）。"""

    evidence_id: PrintableText
    identity: Annotated[EvidenceIdentity, BeforeValidator(_enum_parser(EvidenceIdentity))]
    relation_identity: Annotated[
        RelationIdentity, BeforeValidator(_enum_parser(RelationIdentity))
    ]
    source_ref: SourceRef
    content_hash: Sha256Hex


class TextEvidenceItem(_EvidenceBase):
    """脱敏客户售后消息证据（规格 5.6）：源数据没有消息时间，不设置 occurred_at。"""

    sequence_no: int
    role: Annotated[TextRole, BeforeValidator(_enum_parser(TextRole))]
    text: str = Field(min_length=1)


class ImageEvidenceItem(_EvidenceBase):
    """售后图片证据（规格 5.6）：content_hash 即原文件 SHA-256。"""

    asset_relative_path: RelativePath
    media_type: Annotated[ImageMediaType, BeforeValidator(_enum_parser(ImageMediaType))]


class BehaviorEvidenceItem(_EvidenceBase):
    """确定性程序推导的行为证据（规格 5.6）：模型不得修改数值或重算 RFM。"""

    fact_type: Annotated[
        BehaviorFactType, BeforeValidator(_enum_parser(BehaviorFactType))
    ]
    value: bool | int | float | Amount | Timestamp | str
    calculation_rule: PrintableText | None = None


class EvidenceCollection(_StrictModel):
    """案例证据集合（规格 5.6）：三个数组固定存在；evidence_id 案例内唯一。"""

    text_items: list[TextEvidenceItem] = Field(min_length=1)
    image_items: list[ImageEvidenceItem]
    behavior_items: list[BehaviorEvidenceItem]

    @model_validator(mode="after")
    def _reject_duplicate_evidence_ids(self) -> "EvidenceCollection":
        seen: set[str] = set()
        duplicates: list[str] = []
        for item in (*self.text_items, *self.image_items, *self.behavior_items):
            if item.evidence_id in seen:
                duplicates.append(item.evidence_id)
            seen.add(item.evidence_id)
        if duplicates:
            raise ValueError(f"evidence_id 在案例内必须唯一，重复：{sorted(set(duplicates))}")
        return self


class PrimaryOrder(_StrictModel):
    """主要订单（规格 5.5）：源订单标识、脱敏展示标识、状态、下单时间、
    源中存在的履约时间与聚合付款总额；不保存付款分项与币种。"""

    source_order_id: PrintableText
    order_display_id: PrintableText
    order_status: str = Field(min_length=1)
    order_purchase_timestamp: Timestamp
    payment_total: Amount
    order_approved_at: Timestamp | None = None
    order_delivered_carrier_date: Timestamp | None = None
    order_delivered_customer_date: Timestamp | None = None
    order_estimated_delivery_date: Timestamp | None = None


class Customer(_StrictModel):
    """脱敏客户引用（规格 5.5）：由 customer_unique_id 确定生成，不保存地理字段。"""

    customer_ref: PrintableText


class CustomerValue(_StrictModel):
    """高价值客户结论与 RFM 复算依据（规格 5.3/5.5）：仅供确定性程序复算与追溯。"""

    is_high_value: bool
    rule_version: Literal["high_value_rule_v1"]
    snapshot_at: Timestamp
    recency_days: int
    frequency_orders: int
    monetary_total: Amount
    r_p75: Amount
    m_p80: Amount
    m_p50: Amount
    decision_reason: str = Field(min_length=1)
    source_ref: SourceRef


class Provenance(_StrictModel):
    """组包追溯信息（规格 5.5）：无自由说明字段，Mock 关系由可复算清单表达。"""

    builder_version: PrintableText
    source_manifest_sha256: Sha256Hex
    mapping_manifest_sha256: Sha256Hex
    source_refs: list[SourceRef] = Field(min_length=1)


class CaseInput(_StrictModel):
    """CaseInput v1（规格 5.5；ADR-0018）：顶层只允许这 10 个字段。"""

    schema_version: Literal["case_input.v1"]
    data_version: PrintableText
    batch_id: PrintableText
    case_id: PrintableText
    data_identity: Literal["simulated"]
    primary_order: PrimaryOrder
    customer: Customer
    customer_value: CustomerValue
    evidence: EvidenceCollection
    provenance: Provenance


class BatchManifest(_StrictModel):
    """标准 ZIP manifest.json（规格 5.4）：字段封闭，is_mock 固定为 true。"""

    schema_version: Literal["batch_manifest.v1"]
    data_version: PrintableText
    batch_id: PrintableText
    package_type: Annotated[PackageType, BeforeValidator(_enum_parser(PackageType))]
    is_mock: Literal[True]
    source_snapshot_at: Timestamp
    case_files: list[CaseFilePath]
    case_count: int = Field(ge=1, le=20)
    evidence_count: int = Field(ge=0)

    @model_validator(mode="after")
    def _validate_case_files(self) -> "BatchManifest":
        if self.case_count != len(self.case_files):
            raise ValueError("case_count 必须等于 case_files 的实际数量")
        if len(set(self.case_files)) != len(self.case_files):
            raise ValueError("case_files 不得包含重复路径")
        if self.case_files != sorted(self.case_files):
            raise ValueError("case_files 必须按路径升序排列")
        return self


class Checksums(RootModel[dict[RelativePath, Sha256Hex]]):
    """checksums.json（规格 5.4）：相对路径 → 小写 SHA-256，不含自身。"""

    @model_validator(mode="after")
    def _normalize_and_reject_self(self) -> "Checksums":
        if "checksums.json" in self.root:
            raise ValueError("checksums.json 不得包含自身条目")
        self.root = dict(sorted(self.root.items()))
        return self
