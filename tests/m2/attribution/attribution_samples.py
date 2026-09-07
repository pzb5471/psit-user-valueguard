"""M2-06 验收样例：感知结果与获准证据内容（规格第 7.1、7.2、9.2 节）。

只供归因阶段测试构造合法输入与模型输出变体，不是运行时代码。
证据内容为已脱敏、已按证据类型格式化的单行文本（由调用方从 CaseInput 派生）。
模块名使用 attribution_samples，避免与其它测试目录的样例模块同名冲突。
"""

from __future__ import annotations

import json
from typing import Any

from app.contracts.analysis import PerceptionResult

CASE_ID = "case-0001"

CASE_EVIDENCE_IDS = frozenset({"msg-001", "msg-002", "img-001", "ord-001"})

EVIDENCE_CONTENT: dict[str, str] = {
    "msg-001": "（CUSTOMER）我买的搅拌机用了三天就冒烟了，你们必须给我说法。",
    "msg-002": "（SERVICE_AGENT）非常抱歉，我们会为您登记处理，请稍等。",
    "img-001": "（IMAGE）客户上传的冒烟搅拌机照片，已由感知阶段观察。",
    "ord-001": "（ORDER）订单已支付，金额按十进制定点字符串记录。",
}


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
    return PerceptionResult.model_validate_json(json.dumps(perception_raw(), ensure_ascii=False))


def attribution_json(**overrides: Any) -> str:
    sample: dict[str, Any] = {
        "schema_version": "v1",
        "case_id": CASE_ID,
        "risk_summary": "商品安全问题未解决，客户情绪不耐烦，存在流失风险。",
        "primary_cause": {
            "category": "PRODUCT_ISSUE",
            "explanation": "客户描述与图片烧焦痕迹相互支持，商品质量问题是当前可信假设。",
            "evidence_ids": ["msg-001", "img-001"],
            "counter_evidence_ids": ["msg-002"],
        },
        "alternative_cause": {
            "category": "SERVICE_COMMUNICATION",
            "explanation": "客服仅承诺登记但未给处理方案，沟通问题可能叠加。",
            "evidence_ids": ["msg-002"],
        },
    }
    sample.update(overrides)
    return json.dumps(sample, ensure_ascii=False)


def insufficient_evidence_json() -> str:
    sample: dict[str, Any] = {
        "schema_version": "v1",
        "case_id": CASE_ID,
        "risk_summary": "现有证据不足以可靠判断风险原因。",
        "primary_cause": {
            "category": "INSUFFICIENT_EVIDENCE",
            "explanation": "客户声称与图片观察存在冲突，缺少质检与物流记录佐证。",
            "evidence_ids": [],
        },
    }
    return json.dumps(sample, ensure_ascii=False)
