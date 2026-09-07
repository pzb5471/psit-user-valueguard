"""M2-08 验收样例：案例输入、三阶段合法输出与脚本化失败（规格第 9 节）。

只供引擎测试构造合法输入与输出变体，不是运行时代码。
样例自包含，不导入其它测试目录的模块。
"""

from __future__ import annotations

import json
from typing import Any

from app.contracts.data import CASE_INPUT_SCHEMA_VERSION, CaseInput

TRACE_ID = "trace-0001"
CASE_ID = "case-0001"

_OLIST_ORDERS_CSV = (
    "source_data/ecommercedata-main/data/"
    "Olist-Brazilian-E-Commerce/olist_orders_dataset.csv"
)
_SERVICE_TASKS_JSON = "source_data/ecommercedata-main/data/service_tasks.json"
_HASH_A = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
_HASH_B = "cafecafecafecafecafecafecafecafecafecafecafecafecafecafecafecafe"
_HASH_D = "feedfeedfeedfeedfeedfeedfeedfeedfeedfeedfeedfeedfeedfeedfeedfeed"
_HASH_F = "1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
_HASH_G = "89abcdef89abcdef89abcdef89abcdef89abcdef89abcdef89abcdef89abcdef"


def case_input_raw(**overrides: Any) -> dict[str, Any]:
    sample: dict[str, Any] = {
        "schema_version": CASE_INPUT_SCHEMA_VERSION,
        "data_version": "mock_dataset_v1",
        "batch_id": "batch-demo-0001",
        "case_id": CASE_ID,
        "data_identity": "simulated",
        "primary_order": {
            "source_order_id": "ord-src-0001",
            "order_display_id": "ord-0001",
            "order_status": "delivered",
            "order_purchase_timestamp": "2018-05-10T11:20:00Z",
            "payment_total": "189.90",
        },
        "customer": {"customer_ref": "cust-0001"},
        "customer_value": {
            "is_high_value": True,
            "rule_version": "high_value_rule_v1",
            "snapshot_at": "2018-10-17T17:30:18Z",
            "recency_days": 160,
            "frequency_orders": 3,
            "monetary_total": "820.45",
            "r_p75": "397",
            "m_p80": "209.604",
            "m_p50": "108.0",
            "decision_reason": "R 与 M 均达到高价值分位边界，判定为高价值客户。",
            "source_ref": {
                "dataset": "olist_orders",
                "relative_path": _OLIST_ORDERS_CSV,
                "record_key": "ord-src-0001",
            },
        },
        "evidence": {
            "text_items": [
                {
                    "evidence_id": "msg-0001",
                    "identity": "observed",
                    "relation_identity": "mock_mapped",
                    "source_ref": {
                        "dataset": "service_tasks",
                        "relative_path": _SERVICE_TASKS_JSON,
                        "record_key": "dialog-0001",
                        "field": "first_query",
                    },
                    "content_hash": _HASH_A,
                    "sequence_no": 1,
                    "role": "CUSTOMER",
                    "text": "我买的搅拌机用了三天就冒烟了，必须给我一个说法。",
                },
                {
                    "evidence_id": "msg-0002",
                    "identity": "observed",
                    "relation_identity": "mock_mapped",
                    "source_ref": {
                        "dataset": "service_tasks",
                        "relative_path": _SERVICE_TASKS_JSON,
                        "record_key": "dialog-0001",
                        "field": "first_response",
                    },
                    "content_hash": _HASH_B,
                    "sequence_no": 2,
                    "role": "SERVICE_AGENT",
                    "text": "非常抱歉给您带来不便，我们马上为您登记处理。",
                },
            ],
            "image_items": [],
            "behavior_items": [
                {
                    "evidence_id": "beh-0001",
                    "identity": "observed",
                    "relation_identity": "mock_mapped",
                    "source_ref": {
                        "dataset": "olist_orders",
                        "relative_path": _OLIST_ORDERS_CSV,
                        "record_key": "ord-src-0001",
                        "field": "order_status",
                    },
                    "content_hash": _HASH_D,
                    "fact_type": "ORDER_STATUS",
                    "value": "delivered",
                }
            ],
        },
        "provenance": {
            "builder_version": "case_builder.v1",
            "source_manifest_sha256": _HASH_F,
            "mapping_manifest_sha256": _HASH_G,
            "source_refs": [
                {
                    "dataset": "olist_orders",
                    "relative_path": _OLIST_ORDERS_CSV,
                    "record_key": "ord-src-0001",
                }
            ],
        },
    }
    sample.update(overrides)
    return sample


def loaded_case_input() -> CaseInput:
    return CaseInput.model_validate_json(json.dumps(case_input_raw(), ensure_ascii=False))


def loaded_case_input_with_image() -> CaseInput:
    raw = case_input_raw()
    raw["evidence"]["image_items"] = [
        {
            "evidence_id": "img-0001",
            "identity": "observed",
            "relation_identity": "mock_mapped",
            "source_ref": {
                "dataset": "service_tasks",
                "relative_path": _SERVICE_TASKS_JSON,
                "record_key": "dialog-0001",
                "field": "image",
            },
            "content_hash": _HASH_B,
            "asset_relative_path": "assets/img_0001.jpg",
            "media_type": "image/jpeg",
        }
    ]
    return CaseInput.model_validate_json(json.dumps(raw, ensure_ascii=False))


def perception_json() -> str:
    sample: dict[str, Any] = {
        "schema_version": "v1",
        "case_id": CASE_ID,
        "events": [
            {
                "event_no": 1,
                "category": "商品质量",
                "summary": "客户声称搅拌机使用三天后冒烟。",
                "statement_basis": "CUSTOMER_CLAIMED",
                "resolution": "UNRESOLVED",
                "evidence_ids": ["msg-0001"],
            }
        ],
        "emotion": {"value": "IMPATIENT", "evidence_ids": ["msg-0001"]},
        "missing_evidence": ["缺少商品质检报告。"],
    }
    return json.dumps(sample, ensure_ascii=False)


def attribution_json() -> str:
    sample: dict[str, Any] = {
        "schema_version": "v1",
        "case_id": CASE_ID,
        "risk_summary": "商品安全问题未解决，存在流失风险。",
        "primary_cause": {
            "category": "PRODUCT_ISSUE",
            "explanation": "客户描述与图片观察一致，商品质量问题是当前可信假设。",
            "evidence_ids": ["msg-0001"],
        },
    }
    return json.dumps(sample, ensure_ascii=False)


def strategy_json() -> str:
    sample: dict[str, Any] = {
        "schema_version": "v1",
        "case_id": CASE_ID,
        "intervention_level": "MUST_INTERVENE",
        "priority_reason": "未解决的商品安全问题直接影响客户留存。",
        "actions": [
            {
                "action_type": "EVIDENCE_CHECK",
                "description": "向质检方核实商品烧焦原因。",
                "reason": "商品安全问题尚未确认，需要补充证据。",
                "evidence_ids": ["msg-0001"],
            }
        ],
        "communication_points": ["先向客户说明已启动质量核实。"],
    }
    return json.dumps(sample, ensure_ascii=False)


def broken_perception_json() -> str:
    """缺少 emotion 必填字段：结构校验失败，触发一次定向修复。"""
    sample: dict[str, Any] = {
        "schema_version": "v1",
        "case_id": CASE_ID,
        "events": [
            {
                "event_no": 1,
                "category": "商品质量",
                "summary": "客户声称搅拌机使用三天后冒烟。",
                "statement_basis": "CUSTOMER_CLAIMED",
                "resolution": "UNRESOLVED",
                "evidence_ids": ["msg-0001"],
            }
        ],
    }
    return json.dumps(sample, ensure_ascii=False)
