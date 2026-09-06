"""M1-01 合同验收：CaseInput v1 与三类证据（规格第 5.5、5.6 节）。

面向公开合同边界验证：额外字段、宽松类型（浮点金额、无时区时间）、
跨案例证据重复、缺来源和禁用字段全部被拒绝；合法样例可往返序列化。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.contracts.data import CaseInput, EvidenceBundle, EvidenceRole

pytestmark = pytest.mark.task_m1_01

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "runtime" / "contracts"


def load_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def load_valid_case() -> dict[str, Any]:
    return load_fixture("valid_case_input.json")


class TestValidCaseRoundTrip:
    """合法最小样例必须通过严格校验并支持往返序列化。"""

    def test_valid_fixture_parses_and_round_trips(self) -> None:
        case = CaseInput.model_validate_json(
            (FIXTURE_DIR / "valid_case_input.json").read_text(encoding="utf-8")
        )

        reparsed = CaseInput.model_validate_json(case.model_dump_json())

        assert reparsed == case
        assert case.data_version == "mock_dataset_v1"
        assert case.evidence.text_items[0].role is EvidenceRole.CUSTOMER


class TestForbiddenAndExtraFields:
    """规格第 5.5 节禁止字段与任何额外字段都必须被拒绝。"""

    @pytest.mark.parametrize(
        ("fixture", "forbidden_field"),
        [
            ("invalid_case_input_extra_field.json", "case_trigger"),
        ],
    )
    def test_extra_field_rejected(self, fixture: str, forbidden_field: str) -> None:
        raw = load_fixture(fixture)

        with pytest.raises(ValueError, match=forbidden_field):
            CaseInput.model_validate_json(json.dumps(raw, ensure_ascii=False))

    @pytest.mark.parametrize(
        "forbidden_field",
        ["currency", "mood", "reason", "key_answer", "label", "database_gt"],
    )
    def test_forbidden_fields_rejected(self, forbidden_field: str) -> None:
        raw = load_valid_case()
        raw[forbidden_field] = "demo"

        with pytest.raises(ValueError, match=forbidden_field):
            CaseInput.model_validate_json(json.dumps(raw, ensure_ascii=False))


class TestStrictTypes:
    """宽松类型禁止：浮点金额、无时区时间、错误枚举值一律拒绝。"""

    def test_float_money_rejected(self) -> None:
        raw = load_valid_case()
        raw["primary_order"]["payment_total"] = 189.9

        with pytest.raises(ValueError, match="payment_total"):
            CaseInput.model_validate_json(json.dumps(raw, ensure_ascii=False))

    def test_naive_datetime_rejected(self) -> None:
        raw = load_valid_case()
        raw["primary_order"]["order_purchase_timestamp"] = "2018-05-10T11:20:00"

        with pytest.raises(ValueError, match="order_purchase_timestamp"):
            CaseInput.model_validate_json(json.dumps(raw, ensure_ascii=False))

    def test_unknown_data_version_rejected(self) -> None:
        raw = load_valid_case()
        raw["data_version"] = "mock_dataset_v2"

        with pytest.raises(ValueError, match="data_version"):
            CaseInput.model_validate_json(json.dumps(raw, ensure_ascii=False))


class TestEvidenceRules:
    """规格第 5.6 节：evidence_id 案例内唯一、至少一条客户消息、来源必填。"""

    def test_duplicate_evidence_rejected(self) -> None:
        raw = load_fixture("invalid_case_input_duplicate_evidence.json")

        with pytest.raises(ValueError, match="msg-0001"):
            CaseInput.model_validate_json(json.dumps(raw, ensure_ascii=False))

    def test_case_without_customer_message_rejected(self) -> None:
        raw = load_valid_case()
        raw["evidence"]["text_items"] = [
            item
            for item in raw["evidence"]["text_items"]
            if item["role"] != "CUSTOMER"
        ]

        with pytest.raises(ValueError, match="客户售后消息"):
            CaseInput.model_validate_json(json.dumps(raw, ensure_ascii=False))

    def test_missing_source_ref_rejected(self) -> None:
        raw = load_valid_case()
        del raw["evidence"]["text_items"][0]["source_ref"]

        with pytest.raises(ValueError, match="source_ref"):
            CaseInput.model_validate_json(json.dumps(raw, ensure_ascii=False))

    def test_provenance_without_source_refs_rejected(self) -> None:
        raw = load_valid_case()
        raw["provenance"]["source_refs"] = []

        with pytest.raises(ValueError, match="source_refs"):
            CaseInput.model_validate_json(json.dumps(raw, ensure_ascii=False))

    def test_evidence_bundle_rejects_duplicate_ids_directly(self) -> None:
        items = load_valid_case()["evidence"]["text_items"]
        items[1]["evidence_id"] = items[0]["evidence_id"]

        with pytest.raises(ValueError, match="重复"):
            EvidenceBundle.model_validate_json(json.dumps({"text_items": items}))
