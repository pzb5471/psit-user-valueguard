"""M2-07 验收样例：策略阶段获准输入与模型输出（规格第 7.3、7.4、9.2 节）。

只供策略阶段测试构造合法输入与输出变体，不是运行时代码。
样例自包含，不导入其它测试目录的模块，避免 pytest 子集运行时失败。
"""

from __future__ import annotations

import json
from typing import Any

from app.contracts.analysis import PerceptionResult
from app.modules.analysis.attribution import AttributionStageInput
from app.modules.analysis.strategy import (
    ActionCatalogEntry,
    HighValueConclusion,
)

CASE_ID = "case-0001"

CASE_EVIDENCE_IDS = frozenset({"msg-001", "msg-002", "img-001", "ord-001"})

EVIDENCE_CONTENT: dict[str, str] = {
    "msg-001": "（CUSTOMER）我买的搅拌机用了三天就冒烟了，你们必须给我说法。",
    "msg-002": "（SERVICE_AGENT）非常抱歉，我们会为您登记处理，请稍等。",
    "img-001": "（IMAGE）客户上传的冒烟搅拌机照片，已由感知阶段观察。",
    "ord-001": "（ORDER）订单已支付，金额按十进制定点字符串记录。",
}

CATALOG_VERSION = "v1"

CATALOG_ACTIONS = (
    ActionCatalogEntry(
        action_type="EVIDENCE_CHECK",
        description="补充或核实图片、物流、订单或退款证据",
    ),
    ActionCatalogEntry(
        action_type="CUSTOMER_CONTACT",
        description="建议人工联系客户，并给出沟通重点",
    ),
    ActionCatalogEntry(
        action_type="FULFILLMENT_ESCALATION",
        description="建议升级物流或订单履约处理",
    ),
    ActionCatalogEntry(
        action_type="REPLACEMENT_RETURN_REFUND_CHECK",
        description="建议补发、退货或退款核验",
    ),
    ActionCatalogEntry(
        action_type="APOLOGY_COMPENSATION_RETENTION_REQUEST",
        description="提交但不执行道歉、补偿或挽留申请",
    ),
    ActionCatalogEntry(
        action_type="NO_ACTION_MONITOR",
        description="暂不采取动作，并说明观察或复查理由",
    ),
)

HIGH_VALUE_CONCLUSION = HighValueConclusion(
    is_high_value=True,
    decision_reason="RFM 综合分位达到高价值阈值，规则版本 high_value_rule_v1。",
)


def perception_raw(**overrides: Any) -> dict[str, Any]:
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
                "evidence_ids": ["msg-001"],
            },
            {
                "event_no": 2,
                "category": "服务响应",
                "summary": "客服承诺登记处理，尚无结果。",
                "statement_basis": "SERVICE_AGENT_STATED_OR_PROMISED",
                "resolution": "UNRESOLVED",
                "evidence_ids": ["msg-002"],
            },
        ],
        "image_observations": [
            {
                "image_evidence_id": "img-001",
                "analysis_status": "ANALYZED",
                "observable_facts": ["搅拌机底座有烧焦痕迹。"],
                "relation": "MUTUALLY_SUPPORTS",
                "related_text_evidence_ids": ["msg-001"],
            }
        ],
        "emotion": {"value": "IMPATIENT", "evidence_ids": ["msg-001"]},
        "missing_evidence": ["缺少商品质检报告。"],
    }
    sample.update(overrides)
    return sample


def loaded_perception() -> PerceptionResult:
    return PerceptionResult.model_validate_json(
        json.dumps(perception_raw(), ensure_ascii=False)
    )


def attribution_stage_input() -> AttributionStageInput:
    return AttributionStageInput(
        perception=loaded_perception(),
        evidence_content=dict(EVIDENCE_CONTENT),
    )


def attribution_valid_json() -> str:
    sample: dict[str, Any] = {
        "schema_version": "v1",
        "case_id": CASE_ID,
        "risk_summary": "商品安全问题未解决，客户情绪不耐烦，存在流失风险。",
        "primary_cause": {
            "category": "PRODUCT_ISSUE",
            "explanation": "客户描述与图片烧焦痕迹相互支持，商品质量问题是当前可信假设。",
            "evidence_ids": ["msg-001", "img-001"],
        },
    }
    return json.dumps(sample, ensure_ascii=False)


def strategy_action(**overrides: Any) -> dict[str, Any]:
    sample: dict[str, Any] = {
        "action_type": "EVIDENCE_CHECK",
        "description": "向质检方核实商品烧焦原因，判断是否属于质量问题。",
        "reason": "商品安全问题尚未确认，需要补充证据。",
        "evidence_ids": ["msg-001"],
    }
    sample.update(overrides)
    return sample


def strategy_json(**overrides: Any) -> str:
    sample: dict[str, Any] = {
        "schema_version": "v1",
        "case_id": CASE_ID,
        "intervention_level": "MUST_INTERVENE",
        "priority_reason": "未解决的商品安全问题直接影响客户留存。",
        "actions": [strategy_action()],
        "communication_points": ["先向客户说明已启动质量核实。"],
    }
    sample.update(overrides)
    return json.dumps(sample, ensure_ascii=False)


def no_intervention_json() -> str:
    return strategy_json(
        intervention_level="NO_IMMEDIATE_INTERVENTION",
        priority_reason="当前事项影响有限，暂观察即可。",
    )
