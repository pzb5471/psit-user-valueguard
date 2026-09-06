"""M2-05 验收样例：CaseInput v1 案例与感知模型输出（规格第 5.5、5.6、7.1 节）。

只供感知阶段测试构造合法输入与输出变体，不是运行时代码。
样例自包含，不导入其它测试目录的模块。
"""

from __future__ import annotations

import json
from typing import Any

from app.contracts.data import CaseInput

CASE_ID = "case-0001"

_PNG_BYTES = b"\x89PNG\r\n\x1a\nfake-frame"

_OLIST_ORDERS_CSV = (
    "source_data/ecommercedata-main/data/"
    "Olist-Brazilian-E-Commerce/olist_orders_dataset.csv"
)
_OLIST_PAYMENTS_CSV = (
    "source_data/ecommercedata-main/data/"
    "Olist-Brazilian-E-Commerce/olist_order_payments_dataset.csv"
)
_SERVICE_TASKS_JSON = "source_data/ecommercedata-main/data/service_tasks.json"
_SERVICE_IMAGE_JPG = "source_data/ecommercedata-main/data/images/img_0001.jpg"

_HASH_A = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
_HASH_B = "cafecafecafecafecafecafecafecafecafecafecafecafecafecafecafecafe"
_HASH_C = "beefbeefbeefbeefbeefbeefbeefbeefbeefbeefbeefbeefbeefbeefbeefbeef"
_HASH_D = "feedfeedfeedfeedfeedfeedfeedfeedfeedfeedfeedfeedfeedfeedfeedfeed"
_HASH_E = "deaddeaddeaddeaddeaddeaddeaddeaddeaddeaddeaddeaddeaddeaddeaddead"
_HASH_F = "1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
_HASH_G = "89abcdef89abcdef89abcdef89abcdef89abcdef89abcdef89abcdef89abcdef"


def case_input_raw(**overrides: Any) -> dict[str, Any]:
    sample: dict[str, Any] = {
        "schema_version": "v1",
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
            "order_delivered_customer_date": "2018-05-20T15:00:00Z",
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
            "image_items": [
                {
                    "evidence_id": "img-0001",
                    "identity": "observed",
                    "relation_identity": "mock_mapped",
                    "source_ref": {
                        "dataset": "service_images",
                        "relative_path": _SERVICE_IMAGE_JPG,
                        "record_key": "img_0001",
                    },
                    "content_hash": _HASH_C,
                    "asset_relative_path": "assets/img_0001.jpg",
                    "media_type": "image/jpeg",
                }
            ],
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
                },
                {
                    "evidence_id": "beh-0002",
                    "identity": "derived",
                    "relation_identity": "mock_mapped",
                    "source_ref": {
                        "dataset": "olist_payments",
                        "relative_path": _OLIST_PAYMENTS_CSV,
                        "record_key": "ord-src-0001",
                    },
                    "content_hash": _HASH_E,
                    "fact_type": "ORDER_PAYMENT_TOTAL",
                    "value": "189.90",
                    "calculation_rule": "按订单聚合全部付款行的 payment_value 求和。",
                },
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


def perception_valid_json() -> str:
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
            },
            {
                "event_no": 2,
                "category": "服务响应",
                "summary": "客服承诺登记处理，尚无结果。",
                "statement_basis": "SERVICE_AGENT_STATED_OR_PROMISED",
                "resolution": "UNRESOLVED",
                "evidence_ids": ["msg-0002"],
            },
        ],
        "image_observations": [
            {
                "image_evidence_id": "img-0001",
                "analysis_status": "ANALYZED",
                "observable_facts": ["搅拌机底座有烧焦痕迹。"],
                "relation": "MUTUALLY_SUPPORTS",
                "related_text_evidence_ids": ["msg-0001"],
            }
        ],
        "emotion": {"value": "IMPATIENT", "evidence_ids": ["msg-0001"]},
        "missing_evidence": ["缺少商品质检报告。"],
    }
    return json.dumps(sample, ensure_ascii=False)


def perception_unknown_image_json() -> str:
    sample: dict[str, Any] = {
        "schema_version": "v1",
        "case_id": CASE_ID,
        "events": [
            {
                "event_no": 1,
                "category": "商品质量",
                "summary": "客户声称搅拌机冒烟。",
                "statement_basis": "CUSTOMER_CLAIMED",
                "resolution": "UNRESOLVED",
                "evidence_ids": ["msg-0001"],
            }
        ],
        "image_observations": [
            {
                "image_evidence_id": "img-0001",
                "analysis_status": "UNKNOWN",
                "relation": "UNDETERMINED",
            }
        ],
        "emotion": {"value": "UNDETERMINED", "evidence_ids": ["msg-0001"]},
    }
    return json.dumps(sample, ensure_ascii=False)
