"""M2-04 验收样例：合法三阶段结果与可变异的原始 JSON（规格第 5.6、7、9.4 节）。

只供校验器测试构造合法样例与负向变体，不是运行时代码。
证据语义取自规格第 5.6 节；允许证据集合作为参数由测试提供，
校验器不依赖 M1-01 的数据合同代码。
"""

from __future__ import annotations

import json
from typing import Any

CASE_ID = "case-0001"

CASE_EVIDENCE_IDS = frozenset({"msg-001", "msg-002", "img-001", "ord-001"})

PERCEPTION_CITED_IDS = frozenset({"msg-001", "img-001"})

CATALOG_ACTION_TYPES = frozenset(
    {
        "EVIDENCE_CHECK",
        "CUSTOMER_CONTACT",
        "FULFILLMENT_ESCALATION",
        "REPLACEMENT_RETURN_REFUND_CHECK",
        "APOLOGY_COMPENSATION_RETENTION_REQUEST",
        "NO_ACTION_MONITOR",
    }
)


def perception_raw(**overrides: Any) -> dict[str, Any]:
    sample: dict[str, Any] = {
        "schema_version": "v1",
        "case_id": CASE_ID,
        "events": [
            {
                "event_no": 1,
                "category": "物流进度",
                "summary": "客户声称包裹滞留在承运方中转站超过五天。",
                "statement_basis": "CUSTOMER_CLAIMED",
                "resolution": "UNRESOLVED",
                "evidence_ids": ["msg-001"],
            }
        ],
        "image_observations": [
            {
                "image_evidence_id": "img-001",
                "analysis_status": "ANALYZED",
                "observable_facts": ["包裹外包装完整，无可见破损。"],
                "relation": "SUPPLEMENTS",
                "related_text_evidence_ids": ["msg-001"],
            }
        ],
        "emotion": {"value": "IMPATIENT", "evidence_ids": ["msg-001"]},
        "missing_evidence": ["缺少承运方最新扫描记录。"],
    }
    sample.update(overrides)
    return sample


def attribution_raw(**overrides: Any) -> dict[str, Any]:
    sample: dict[str, Any] = {
        "schema_version": "v1",
        "case_id": CASE_ID,
        "risk_summary": "履约异常长时间未解决，存在流失风险。",
        "primary_cause": {
            "category": "LOGISTICS_FULFILLMENT",
            "explanation": "物流状态长期未更新与客户描述一致，属于履约异常假设。",
            "evidence_ids": ["msg-001", "img-001"],
        },
    }
    sample.update(overrides)
    return sample


def strategy_action_raw(**overrides: Any) -> dict[str, Any]:
    sample: dict[str, Any] = {
        "action_type": "EVIDENCE_CHECK",
        "description": "向承运方核实包裹当前所在节点与预计送达时间。",
        "reason": "履约异常尚未解决，需要补充物流证据。",
        "evidence_ids": ["msg-001"],
    }
    sample.update(overrides)
    return sample


def strategy_raw(**overrides: Any) -> dict[str, Any]:
    sample: dict[str, Any] = {
        "schema_version": "v1",
        "case_id": CASE_ID,
        "intervention_level": "MUST_INTERVENE",
        "priority_reason": "未解决的履约异常直接影响客户留存。",
        "actions": [strategy_action_raw()],
        "communication_points": ["先向客户同步已核实的物流进展。"],
    }
    sample.update(overrides)
    return sample


def to_raw_json(sample: dict[str, Any]) -> str:
    """按规格第 9.4 节真实路径序列化为模型输出 JSON。"""

    return json.dumps(sample, ensure_ascii=False)
