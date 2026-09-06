"""M2-01 合同验收：动作目录 action_catalog.v1.json（规格第 7.3 节）。

目录是只读数据文件。测试以规格第 7.3 节原文为独立真源：
版本、六个动作代码唯一、业务含义逐字一致，且不携带额外字段。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.contracts.analysis import ACTION_CATALOG_VERSION, ActionType

pytestmark = pytest.mark.task_m2_01

REPO_ROOT = Path(__file__).resolve().parents[3]
CATALOG_PATH = REPO_ROOT / "config" / "action_catalog.v1.json"

# 独立真源：规格第 7.3 节动作目录表的逐字业务含义。
SPEC_ACTION_MEANINGS = {
    "EVIDENCE_CHECK": "补充或核实图片、物流、订单或退款证据",
    "CUSTOMER_CONTACT": "建议人工联系客户，并给出沟通重点",
    "FULFILLMENT_ESCALATION": "建议升级物流或订单履约处理",
    "REPLACEMENT_RETURN_REFUND_CHECK": "建议补发、退货或退款核验",
    "APOLOGY_COMPENSATION_RETENTION_REQUEST": "提交但不执行道歉、补偿或挽留申请",
    "NO_ACTION_MONITOR": "暂不采取动作，并说明观察或复查理由",
}


def load_catalog() -> dict:
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def test_catalog_exists_at_frozen_path() -> None:
    assert CATALOG_PATH.is_file(), f"缺少动作目录文件：{CATALOG_PATH}"


def test_catalog_version_matches_contract_constant() -> None:
    assert load_catalog()["catalog_version"] == ACTION_CATALOG_VERSION == "v1"


def test_catalog_has_exactly_six_unique_actions() -> None:
    entries = load_catalog()["actions"]
    types = [entry["action_type"] for entry in entries]
    assert len(types) == 6
    assert len(set(types)) == 6
    assert set(types) == {member.value for member in ActionType}


def test_catalog_descriptions_match_spec_text_verbatim() -> None:
    for entry in load_catalog()["actions"]:
        assert entry["description"] == SPEC_ACTION_MEANINGS[entry["action_type"]]


def test_catalog_carries_no_extra_fields() -> None:
    catalog = load_catalog()
    assert set(catalog.keys()) == {"catalog_version", "actions"}
    for entry in catalog["actions"]:
        assert set(entry.keys()) == {"action_type", "description"}
