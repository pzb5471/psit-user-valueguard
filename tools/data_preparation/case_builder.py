"""M1-09 案例构造：由主表行、任务记录与 RFM 结果生成 CaseInput 字典（技术实施规格 5.5—5.6）。

- 主订单选择：任务对话 strip 后与主表 conversation 精确匹配，命中多个订单时取
  order_id 最小者；同 order_id 的多条付款行按 Decimal 聚合 payment_total。
- 文本证据：每行一条，role 取 CUSTOMER/SERVICE_AGENT，文本为脱敏结果；
  content_hash=SHA-256(脱敏文本 UTF-8)。
- 图片证据：按任务 image_paths 顺序编号，扩展名按魔数推导（jpeg→.jpg、png→.png、
  gif→.gif）；content_hash=原文件 SHA-256。
- 行为证据：只允许规格 5.6 的 8 个 fact_type；空白时间省略该项而不是写 null；
  HIGH_VALUE_CUSTOMER 带 calculation_rule="high_value_rule_v1"。
- 密封参考：任务中的答案/标签/轨迹/未脱敏地址等字段绝不进入运行包，只提取到
  sealed/ 参考 JSON（answer 泄漏扫描键清单与 zip_stage 保持一致）。
- 本模块只构造 dict，最终由 builder 统一过 CaseInput/BatchManifest 合同校验。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from .conversation import split_conversation
from .rfm import CustomerProfile, RfmThresholds
from .sanitize import sanitize_conversation
from .sources import (
    CSV_DATASET_NAME,
    CSV_RELATIVE_PATH,
    TASKS_DATASET_NAME,
    TASKS_RELATIVE_PATH,
    non_empty,
    to_iso_timestamp,
)

# 与 zip_stage 泄漏扫描保持一致：这些键只进 sealed 参考，绝不进运行包。
SEALED_KEYS = (
    "user_profile_st1",
    "key_answer",
    "label",
    "database_gt",
    "question_type",
    "user_address",
    "database",
    "first_query",
    "trajectory",
    "user_profile",
)

CASE_INPUT_SCHEMA_VERSION = "case_input.v1"
DATA_VERSION = "mock_dataset_v1"
DATA_IDENTITY = "simulated"
RELATION_IDENTITY = "mock_mapped"
RULE_VERSION = "high_value_rule_v1"
BUILDER_VERSION = "mock_dataset_builder.v1"

# 图片魔数 → (media_type, 扩展名)；按魔数推导扩展名（源文件名不可靠）。
_IMAGE_MAGIC: tuple[tuple[tuple[str, str], bytes], ...] = (
    (("image/jpeg", ".jpg"), b"\xff\xd8\xff"),
    (("image/png", ".png"), b"\x89PNG\r\n\x1a\n"),
    (("image/gif", ".gif"), b"GIF87a"),
    (("image/gif", ".gif"), b"GIF89a"),
)

# 行为证据 8 个 fact_type 的锁定顺序。
_BEHAVIOR_ORDER = (
    "HIGH_VALUE_CUSTOMER",
    "ORDER_STATUS",
    "ORDER_PURCHASED_AT",
    "ORDER_APPROVED_AT",
    "ORDER_DELIVERED_TO_CARRIER_AT",
    "ORDER_DELIVERED_TO_CUSTOMER_AT",
    "ORDER_ESTIMATED_DELIVERY_AT",
    "ORDER_PAYMENT_TOTAL",
)

_BEHAVIOR_FACT_CSV_FIELDS = {
    "ORDER_STATUS": "order_status",
    "ORDER_PURCHASED_AT": "order_purchase_timestamp",
    "ORDER_APPROVED_AT": "order_approved_at",
    "ORDER_DELIVERED_TO_CARRIER_AT": "order_delivered_carrier_date",
    "ORDER_DELIVERED_TO_CUSTOMER_AT": "order_delivered_customer_date",
    "ORDER_ESTIMATED_DELIVERY_AT": "order_estimated_delivery_date",
    "ORDER_PAYMENT_TOTAL": "payment_value",
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def _deterministic_sha256(parts: list[bytes]) -> str:
    """把多个字节段按给定顺序拼接后取 SHA-256（确定性摘要）。"""
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part)
    return digest.hexdigest()


def hashable_json_value(value: object) -> object:
    """把 Decimal/datetime 规范化为可 JSON 序列化标量（其余原样返回）。"""
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def behavior_value_hash(value: object) -> str:
    """行为证据 content_hash：规范化后按 JSON 序列化取 SHA-256。"""
    return sha256_text(json.dumps(hashable_json_value(value), ensure_ascii=False))


def detect_image(kind: str) -> tuple[str, str] | None:
    """由文件头魔数推导 (media_type, 扩展名)；无法识别返回 None。"""
    if kind.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", ".jpg"
    if kind.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", ".png"
    if kind.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif", ".gif"
    return None


@dataclass(frozen=True)
class MainOrder:
    """主订单：主行 + 同 order_id 全部付款行。"""

    main_row: dict[str, str]
    rows: list[dict[str, str]]

    @property
    def order_id(self) -> str:
        return self.main_row["order_id"]

    @property
    def customer_unique_id(self) -> str:
        return self.main_row["customer_unique_id"]

    def payment_total(self) -> Decimal:
        total = Decimal("0")
        for row in self.rows:
            total += Decimal(row["payment_value"])
        return total


def match_main_order(rows: list[dict[str, str]], conversation: str) -> MainOrder | None:
    """按锁定规则选择主订单：strip 精确匹配，命中多个取 order_id 最小者。

    返回 None 表示源数据中没有与任务对话匹配的行（调用方视为源数据错误）。
    """
    needle = conversation.strip()
    if not needle:
        return None
    matched = [
        idx
        for idx, row in enumerate(rows)
        if (row.get("conversation") or "").strip() == needle
    ]
    if not matched:
        return None
    first_idx = min(matched, key=lambda idx: rows[idx]["order_id"])
    order_id = rows[first_idx]["order_id"]
    order_rows = [row for row in rows if row["order_id"] == order_id]
    return MainOrder(main_row=rows[first_idx], rows=order_rows)


def task_source_ref(task_id: str, field: str | None = None) -> dict[str, str]:
    ref: dict[str, str] = {
        "dataset": TASKS_DATASET_NAME,
        "relative_path": TASKS_RELATIVE_PATH,
        "record_key": task_id,
    }
    if field is not None:
        ref["field"] = field
    return ref


def csv_source_ref(customer_unique_id: str) -> dict[str, str]:
    return {
        "dataset": CSV_DATASET_NAME,
        "relative_path": CSV_RELATIVE_PATH,
        "record_key": customer_unique_id,
    }


def build_text_items(
    task_id: str,
    conversation: str,
    source_ref: dict[str, str] | None = None,
) -> list[dict[str, object]]:
    """按拆分规则生成脱敏文本证据（含每行 content_hash）。"""
    if source_ref is None:
        source_ref = task_source_ref(task_id, "conversation")
    items: list[dict[str, object]] = []
    for seq, item in enumerate(split_conversation(conversation), start=1):
        text = str(item["text"])
        sanitized = sanitize_conversation(text)
        items.append(
            {
                "evidence_id": f"ev_text_{seq:03d}",
                "identity": "observed",
                "relation_identity": RELATION_IDENTITY,
                "source_ref": source_ref,
                "content_hash": sha256_text(sanitized),
                "sequence_no": int(item["sequence_no"]),
                "role": str(item["role"]),
                "text": sanitized,
            }
        )
    return items


def build_image_items(
    source_root: Path,
    task_id: str,
    image_paths: list[str],
    case_id: str,
) -> tuple[list[dict[str, object]], dict[str, bytes]]:
    """读取任务图片并生成图片证据；返回 (证据列表, 资产字节映射)。"""
    items: list[dict[str, object]] = []
    assets: dict[str, bytes] = {}
    for idx, rel in enumerate(image_paths, start=1):
        path = source_root / rel
        data = path.read_bytes()
        media_type, extension = detect_image(data[:16]) or (None, None)
        if media_type is None:
            raise ValueError(f"无法识别图片类型：{rel}（魔数未知）")
        asset_relative_path = f"assets/{case_id}/{idx:02d}{extension}"
        items.append(
            {
                "evidence_id": f"ev_image_{idx:03d}",
                "identity": "observed",
                "relation_identity": RELATION_IDENTITY,
                "source_ref": task_source_ref(task_id, "image_paths"),
                "content_hash": sha256_bytes(data),
                "asset_relative_path": asset_relative_path,
                "media_type": media_type,
            }
        )
        assets[asset_relative_path] = data
    return items, assets


def build_behavior_items(
    order: MainOrder,
    profile: CustomerProfile,
    thresholds: RfmThresholds,
) -> list[dict[str, object]]:
    """生成 8 项行为证据（锁定顺序）；空白时间省略该项。"""
    payment_total = order.payment_total()
    values: dict[str, object] = {
        "HIGH_VALUE_CUSTOMER": profile.is_high_value,
        "ORDER_STATUS": order.main_row["order_status"],
        "ORDER_PURCHASED_AT": to_iso_timestamp(
            order.main_row["order_purchase_timestamp"]
        ),
        "ORDER_PAYMENT_TOTAL": format(payment_total, "f"),
    }
    for fact_type in (
        "ORDER_APPROVED_AT",
        "ORDER_DELIVERED_TO_CARRIER_AT",
        "ORDER_DELIVERED_TO_CUSTOMER_AT",
        "ORDER_ESTIMATED_DELIVERY_AT",
    ):
        cell = order.main_row[_BEHAVIOR_FACT_CSV_FIELDS[fact_type]]
        if non_empty(cell):
            values[fact_type] = to_iso_timestamp(cell)

    source_ref = csv_source_ref(order.customer_unique_id)
    items: list[dict[str, object]] = []
    for idx, fact_type in enumerate(_BEHAVIOR_ORDER, start=1):
        if fact_type not in values:
            continue
        item: dict[str, object] = {
            "evidence_id": f"ev_behavior_{idx:03d}",
            "identity": "derived",
            "relation_identity": RELATION_IDENTITY,
            "source_ref": source_ref,
            "content_hash": behavior_value_hash(values[fact_type]),
            "fact_type": fact_type,
            "value": values[fact_type],
        }
        if fact_type == "HIGH_VALUE_CUSTOMER":
            item["calculation_rule"] = RULE_VERSION
        items.append(item)
    return items


def sealed_fields(task: dict[str, object]) -> dict[str, object]:
    """提取任务中的答案/标签/轨迹等字段作为密封参考（只取存在的键）。"""
    extracted: dict[str, object] = {}
    for key in SEALED_KEYS:
        if key in task:
            extracted[key] = task[key]
    return extracted


def build_case_input(
    *,
    task: dict[str, object],
    order: MainOrder,
    profile: CustomerProfile,
    thresholds: RfmThresholds,
    rfm_snapshot_at: datetime,
    batch_id: str,
    case_id: str,
    case_no: int,
    package_prefix: str,
    source_root: Path,
    source_manifest_sha256: str,
    mapping_manifest_sha256: str,
) -> tuple[dict[str, object], dict[str, bytes]]:
    """构造一个 CaseInput 字典与资产映射；字典结构与合同字段一一对应。"""
    task_id = str(task["task_id"])
    conversation = str(task.get("conversation") or "")
    image_paths = [str(p) for p in (task.get("image_paths") or [])]

    text_items = build_text_items(task_id, conversation)
    image_items, assets = build_image_items(source_root, task_id, image_paths, case_id)
    behavior_items = build_behavior_items(order, profile, thresholds)

    main_row = order.main_row
    primary_order: dict[str, object] = {
        "source_order_id": order.order_id,
        "order_display_id": f"ORD-{package_prefix}-{case_no:06d}",
        "order_status": main_row["order_status"],
        "order_purchase_timestamp": to_iso_timestamp(
            main_row["order_purchase_timestamp"]
        ),
        "payment_total": format(order.payment_total(), "f"),
    }
    for key, cell in (
        ("order_approved_at", main_row["order_approved_at"]),
        ("order_delivered_carrier_date", main_row["order_delivered_carrier_date"]),
        ("order_delivered_customer_date", main_row["order_delivered_customer_date"]),
        ("order_estimated_delivery_date", main_row["order_estimated_delivery_date"]),
    ):
        if non_empty(cell):
            primary_order[key] = to_iso_timestamp(cell)

    customer_value: dict[str, object] = {
        "is_high_value": profile.is_high_value,
        "rule_version": RULE_VERSION,
        "snapshot_at": rfm_snapshot_at.isoformat(),
        "recency_days": profile.recency_days,
        "frequency_orders": profile.frequency_orders,
        "monetary_total": format(profile.monetary_total, "f"),
        "r_p75": thresholds.r_p75_text,
        "m_p80": thresholds.m_p80_text,
        "m_p50": thresholds.m_p50_text,
        "decision_reason": profile.decision_reason(thresholds),
        "source_ref": csv_source_ref(order.customer_unique_id),
    }

    payload: dict[str, object] = {
        "schema_version": CASE_INPUT_SCHEMA_VERSION,
        "data_version": DATA_VERSION,
        "batch_id": batch_id,
        "case_id": case_id,
        "data_identity": DATA_IDENTITY,
        "primary_order": primary_order,
        "customer": {"customer_ref": f"CUST-{package_prefix}-{case_no:06d}"},
        "customer_value": customer_value,
        "evidence": {
            "text_items": text_items,
            "image_items": image_items,
            "behavior_items": behavior_items,
        },
        "provenance": {
            "builder_version": BUILDER_VERSION,
            "source_manifest_sha256": source_manifest_sha256,
            "mapping_manifest_sha256": mapping_manifest_sha256,
            "source_refs": [
                csv_source_ref(order.customer_unique_id),
                task_source_ref(task_id),
            ],
        },
    }
    return payload, assets


def build_control_case(
    *,
    rows: list[dict[str, str]],
    profile: CustomerProfile,
    thresholds: RfmThresholds,
    rfm_snapshot_at: datetime,
    source_manifest_sha256: str,
    mapping_manifest_sha256: str,
) -> dict[str, object]:
    """构造普通客户对照案例（不打包进 ZIP，仅作可复算参考）。"""
    if not rows:
        raise ValueError("控制案例客户在主表中不存在")
    main_row = rows[0]
    order_id = main_row["order_id"]
    customer_unique_id = main_row["customer_unique_id"]
    order = MainOrder(main_row=main_row, rows=rows)

    conversation = main_row.get("conversation") or ""
    text_source_ref = csv_source_ref(customer_unique_id)
    text_source_ref["field"] = "conversation"
    text_items = build_text_items(order_id, conversation, text_source_ref)
    # 控制案例沿用行为证据规则（无图片）。
    behavior_items = build_behavior_items(order, profile, thresholds)

    primary_order: dict[str, object] = {
        "source_order_id": order_id,
        "order_display_id": "ORD-CONTROL-000001",
        "order_status": main_row["order_status"],
        "order_purchase_timestamp": to_iso_timestamp(
            main_row["order_purchase_timestamp"]
        ),
        "payment_total": format(order.payment_total(), "f"),
    }
    for key, cell in (
        ("order_approved_at", main_row["order_approved_at"]),
        ("order_delivered_carrier_date", main_row["order_delivered_carrier_date"]),
        ("order_delivered_customer_date", main_row["order_delivered_customer_date"]),
        ("order_estimated_delivery_date", main_row["order_estimated_delivery_date"]),
    ):
        if non_empty(cell):
            primary_order[key] = to_iso_timestamp(cell)

    return {
        "schema_version": CASE_INPUT_SCHEMA_VERSION,
        "data_version": DATA_VERSION,
        "batch_id": "control_case_v1",
        "case_id": "control_case_001",
        "data_identity": DATA_IDENTITY,
        "primary_order": primary_order,
        "customer": {"customer_ref": "CUST-CONTROL-000001"},
        "customer_value": {
            "is_high_value": profile.is_high_value,
            "rule_version": RULE_VERSION,
            "snapshot_at": rfm_snapshot_at.isoformat(),
            "recency_days": profile.recency_days,
            "frequency_orders": profile.frequency_orders,
            "monetary_total": format(profile.monetary_total, "f"),
            "r_p75": thresholds.r_p75_text,
            "m_p80": thresholds.m_p80_text,
            "m_p50": thresholds.m_p50_text,
            "decision_reason": profile.decision_reason(thresholds),
            "source_ref": csv_source_ref(customer_unique_id),
        },
        "evidence": {
            "text_items": text_items,
            "image_items": [],
            "behavior_items": behavior_items,
        },
        "provenance": {
            "builder_version": BUILDER_VERSION,
            "source_manifest_sha256": source_manifest_sha256,
            "mapping_manifest_sha256": mapping_manifest_sha256,
            "source_refs": [csv_source_ref(customer_unique_id)],
        },
    }
