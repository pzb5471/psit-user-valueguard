"""M2-01 合同样例构造器。

只供合同测试构造合法样例与负向变体，不是运行时代码。
所有默认值取自规格第 5.6、7、9 节的冻结边界；字段含义见 analysis.py 文档字符串。
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel


def parse[M: BaseModel](model: type[M], sample: dict[str, Any]) -> M:
    """按规格第 9.4 节真实路径校验合同样例：JSON 解析 + Pydantic 严格校验。"""
    return model.model_validate_json(json.dumps(sample, ensure_ascii=False))


def perception_event(**overrides: Any) -> dict[str, Any]:
    sample: dict[str, Any] = {
        "event_no": 1,
        "category": "物流进度",
        "summary": "客户声称包裹滞留在承运方中转站超过五天。",
        "statement_basis": "CUSTOMER_CLAIMED",
        "resolution": "UNRESOLVED",
        "evidence_ids": ["msg-001"],
    }
    sample.update(overrides)
    return sample


def image_observation(**overrides: Any) -> dict[str, Any]:
    sample: dict[str, Any] = {
        "image_evidence_id": "img-001",
        "analysis_status": "ANALYZED",
        "observable_facts": ["包裹外包装完整，无可见破损。"],
        "relation": "SUPPLEMENTS",
        "related_text_evidence_ids": ["msg-001"],
    }
    sample.update(overrides)
    return sample


def emotion(**overrides: Any) -> dict[str, Any]:
    sample: dict[str, Any] = {
        "value": "IMPATIENT",
        "evidence_ids": ["msg-001"],
    }
    sample.update(overrides)
    return sample


def perception_result(**overrides: Any) -> dict[str, Any]:
    sample: dict[str, Any] = {
        "schema_version": "v1",
        "case_id": "case-0001",
        "events": [perception_event()],
        "image_observations": [image_observation()],
        "emotion": emotion(),
    }
    sample.update(overrides)
    return sample


def cause(**overrides: Any) -> dict[str, Any]:
    sample: dict[str, Any] = {
        "category": "LOGISTICS_FULFILLMENT",
        "explanation": "承运方物流状态迟迟未更新，履约异常与客户描述一致。",
        "evidence_ids": ["msg-001"],
    }
    sample.update(overrides)
    return sample


def attribution_result(**overrides: Any) -> dict[str, Any]:
    sample: dict[str, Any] = {
        "schema_version": "v1",
        "case_id": "case-0001",
        "risk_summary": "订单履约长时间无进展，存在流失风险。",
        "primary_cause": cause(),
    }
    sample.update(overrides)
    return sample


def strategy_action(**overrides: Any) -> dict[str, Any]:
    sample: dict[str, Any] = {
        "action_type": "EVIDENCE_CHECK",
        "description": "向承运方核实包裹当前所在节点与预计送达时间。",
        "reason": "履约异常尚未解决，需要补充物流证据。",
        "evidence_ids": ["msg-001"],
    }
    sample.update(overrides)
    return sample


def decision_package(**overrides: Any) -> dict[str, Any]:
    sample: dict[str, Any] = {
        "schema_version": "v1",
        "case_id": "case-0001",
        "intervention_level": "MUST_INTERVENE",
        "priority_reason": "未解决的履约异常直接影响高价值客户留存。",
        "actions": [strategy_action()],
        "communication_points": ["先向客户同步已核实的物流进展。"],
    }
    sample.update(overrides)
    return sample
