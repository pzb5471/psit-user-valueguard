"""data.py 数据共享合同测试（M1-01）：严格校验、JSON 交换往返与禁用字段拒绝。

以 tests/fixtures/runtime/contracts/ 的合法样例为基底做 JSON 变异，覆盖：
- 合法样例经 model_validate_json 可解析，model_dump_json(exclude_none=True) 后可再次
  解析且关键字段保持类型（Decimal / datetime / 枚举成员）。
- 未声明字段（含规格 5.4/5.5 禁止的答案泄漏字段与顶层字段）一律拒绝。
- 宽松类型一律拒绝（严格模式：float 不能进入金额，数字字符串不能进入 int，
  "true" 不能进入 bool，时间与枚举不接受数字等宽松输入）。
- 重复 evidence_id、缺失来源、路径越界、错误 SHA、manifest 数量/顺序/上限、
  checksums 自身条目等负向场景。
"""

import copy
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.contracts.data import (
    BATCH_MANIFEST_SCHEMA_VERSION,
    CASE_INPUT_SCHEMA_VERSION,
    HIGH_VALUE_RULE_VERSION,
    MOCK_DATA_VERSION,
    BatchManifest,
    BehaviorEvidenceItem,
    BehaviorFactType,
    CaseInput,
    Checksums,
    CustomerValue,
    EvidenceCollection,
    EvidenceIdentity,
    ImageMediaType,
    PackageType,
    PrimaryOrder,
    Provenance,
    RelationIdentity,
    SourceRef,
    TextEvidenceItem,
    TextRole,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "runtime" / "contracts"

_TOP_LEVEL_BANNED_FIELDS = (
    "case_trigger",
    "modality_status",
    "currency",
    "payment_parts",
    "simulated_wait_minutes",
    "behavior_change",
    "window_start",
    "window_end",
)

_ANSWER_LEAK_FIELDS = (
    "mood",
    "reason",
    "solution",
    "image_verification",
    "key_answer",
    "label",
    "database_gt",
    "trajectory",
    "user_profile_st1",
    "user_profile",
    "question_type",
    "user_address",
    "database",
    "first_query",
)


def load_fixture(name: str) -> dict:
    with (FIXTURES_DIR / name).open("r", encoding="utf-8") as f:
        return json.load(f)


def valid_case_input() -> dict:
    return copy.deepcopy(load_fixture("valid_case_input.json"))


def valid_manifest() -> dict:
    return copy.deepcopy(load_fixture("valid_manifest.json"))


def valid_checksums() -> dict:
    return copy.deepcopy(load_fixture("valid_checksums.json"))


def set_nested(payload: dict, loc: tuple, value: Any) -> None:
    node: dict = payload
    for part in loc[:-1]:
        node = node[part]
    node[loc[-1]] = value


def reject(model: Any, payload: Any) -> None:
    with pytest.raises(ValidationError):
        model.model_validate(payload)


def test_all_fixture_files_are_valid_json() -> None:
    for name in (
        "valid_case_input.json",
        "valid_manifest.json",
        "valid_checksums.json",
        "invalid_case_input_banned_field.json",
        "invalid_manifest_mismatch.json",
        "invalid_checksums_self.json",
    ):
        load_fixture(name)


def test_schema_version_constants() -> None:
    assert CASE_INPUT_SCHEMA_VERSION == "case_input.v1"
    assert BATCH_MANIFEST_SCHEMA_VERSION == "batch_manifest.v1"
    assert HIGH_VALUE_RULE_VERSION == "high_value_rule_v1"
    assert MOCK_DATA_VERSION == "mock_dataset_v1"


def test_fixture_schema_versions_match_constants() -> None:
    assert valid_case_input()["schema_version"] == CASE_INPUT_SCHEMA_VERSION
    assert valid_case_input()["data_version"] == MOCK_DATA_VERSION
    assert valid_case_input()["data_identity"] == "simulated"
    assert valid_case_input()["customer_value"]["rule_version"] == HIGH_VALUE_RULE_VERSION
    assert valid_manifest()["schema_version"] == BATCH_MANIFEST_SCHEMA_VERSION
    assert valid_manifest()["is_mock"] is True


def test_enum_members_match_spec() -> None:
    assert {m.value for m in EvidenceIdentity} == {"observed", "derived", "simulated"}
    assert {m.value for m in RelationIdentity} == {"mock_mapped"}
    assert {m.value for m in TextRole} == {"CUSTOMER", "SERVICE_AGENT"}
    assert {m.value for m in ImageMediaType} == {"image/jpeg", "image/png", "image/gif"}
    assert {m.value for m in PackageType} == {"DEMO", "ACCEPTANCE"}
    assert {m.value for m in BehaviorFactType} == {
        "HIGH_VALUE_CUSTOMER",
        "ORDER_STATUS",
        "ORDER_PURCHASED_AT",
        "ORDER_APPROVED_AT",
        "ORDER_DELIVERED_TO_CARRIER_AT",
        "ORDER_DELIVERED_TO_CUSTOMER_AT",
        "ORDER_ESTIMATED_DELIVERY_AT",
        "ORDER_PAYMENT_TOTAL",
    }


def test_behavior_fact_type_has_exactly_eight_members() -> None:
    assert len(BehaviorFactType) == 8


def test_nested_models_validate_directly() -> None:
    raw = valid_case_input()
    SourceRef.model_validate(raw["customer_value"]["source_ref"])
    PrimaryOrder.model_validate(raw["primary_order"])
    CustomerValue.model_validate(raw["customer_value"])
    EvidenceCollection.model_validate(raw["evidence"])
    Provenance.model_validate(raw["provenance"])
    TextEvidenceItem.model_validate(raw["evidence"]["text_items"][0])
    BehaviorEvidenceItem.model_validate(raw["evidence"]["behavior_items"][0])


def test_valid_case_input_typed_scalars() -> None:
    case = CaseInput.model_validate(valid_case_input())
    assert case.schema_version == "case_input.v1"
    assert case.data_identity == "simulated"
    assert isinstance(case.primary_order.payment_total, Decimal)
    assert case.primary_order.payment_total == Decimal("918.16")
    assert isinstance(case.primary_order.order_purchase_timestamp, datetime)
    assert isinstance(case.customer_value.monetary_total, Decimal)
    assert isinstance(case.customer_value.snapshot_at, datetime)
    assert case.evidence.behavior_items[0].value is True
    assert case.evidence.behavior_items[1].value == "delivered"
    assert isinstance(case.evidence.behavior_items[2].value, datetime)
    assert isinstance(case.evidence.behavior_items[3].value, Decimal)
    assert isinstance(case.evidence.text_items[0].role, TextRole)
    assert isinstance(case.evidence.image_items[0].media_type, ImageMediaType)
    assert isinstance(case.evidence.behavior_items[0].fact_type, BehaviorFactType)


def test_valid_case_input_json_round_trip() -> None:
    first = CaseInput.model_validate_json(json.dumps(valid_case_input()))
    dumped = first.model_dump_json(exclude_none=True)
    second = CaseInput.model_validate_json(dumped)
    assert second.model_dump_json(exclude_none=True) == dumped


def test_model_dump_keeps_decimal_python_type() -> None:
    case = CaseInput.model_validate(valid_case_input())
    dumped = case.model_dump()
    assert dumped["primary_order"]["payment_total"] == Decimal("918.16")
    assert isinstance(dumped["primary_order"]["payment_total"], Decimal)


def test_valid_manifest_round_trip() -> None:
    first = BatchManifest.model_validate_json(json.dumps(valid_manifest()))
    dumped = first.model_dump_json(exclude_none=True)
    second = BatchManifest.model_validate_json(dumped)
    assert second.model_dump_json(exclude_none=True) == dumped


def test_valid_checksums_round_trip() -> None:
    first = Checksums.model_validate_json(json.dumps(valid_checksums()))
    dumped = first.model_dump_json()
    second = Checksums.model_validate_json(dumped)
    assert second.model_dump_json() == dumped


@pytest.mark.parametrize("field", _TOP_LEVEL_BANNED_FIELDS)
def test_top_level_banned_fields_rejected(field: str) -> None:
    payload = valid_case_input()
    payload[field] = "任意值"
    reject(CaseInput, payload)


@pytest.mark.parametrize("field", _ANSWER_LEAK_FIELDS)
def test_answer_leak_fields_rejected(field: str) -> None:
    payload = valid_case_input()
    payload[field] = "客户同意换货"
    reject(CaseInput, payload)


@pytest.mark.parametrize(
    ("loc", "value"),
    [
        (("primary_order", "shipping_fee"), "10.00"),
        (("customer", "city"), "上海"),
        (("evidence", "audio_items"), []),
        (("evidence", "text_items", 0, "occurred_at"), "2018-03-12T09:25:00"),
        (("evidence", "behavior_items", 0, "confidence"), 0.9),
        (("customer_value", "source_ref", "table"), "orders"),
        (("provenance", "note"), "自由说明"),
        (("schema_version",), "batch_manifest.v1"),
        (("data_identity",), "real"),
        (("customer_value", "rule_version"), "high_value_rule_v2"),
    ],
)
def test_nested_extra_and_literal_rejected(loc: tuple, value: Any) -> None:
    payload = valid_case_input()
    set_nested(payload, loc, value)
    reject(CaseInput, payload)


@pytest.mark.parametrize(
    ("loc", "value"),
    [
        (("primary_order", "payment_total"), 918.16),
        (("customer_value", "monetary_total"), 2860.42),
        (("customer_value", "is_high_value"), "true"),
        (("evidence", "text_items", 0, "sequence_no"), "1"),
        (("primary_order", "order_purchase_timestamp"), 1530000000),
        (("primary_order", "order_purchase_timestamp"), "2018-13-99"),
        (("primary_order", "order_purchase_timestamp"), "不是时间"),
        (("evidence", "text_items", 0, "role"), "ADMIN"),
        (("evidence", "text_items", 0, "identity"), "real"),
        (("evidence", "text_items", 0, "identity"), 5),
        (("evidence", "image_items", 0, "media_type"), "image/bmp"),
        (("evidence", "behavior_items", 0, "fact_type"), "ORDER_REFUNDED"),
        (("evidence", "behavior_items", 0, "relation_identity"), "manual"),
    ],
)
def test_strict_type_and_enum_rejected(loc: tuple, value: Any) -> None:
    payload = valid_case_input()
    set_nested(payload, loc, value)
    reject(CaseInput, payload)


@pytest.mark.parametrize(
    ("loc", "value"),
    [
        (("schema_version",), "case_input.v1"),
        (("is_mock",), False),
        (("package_type",), "PROD"),
        (("source_snapshot_at",), 1530000000),
        (("evidence_count",), -1),
    ],
)
def test_manifest_literals_and_types_rejected(loc: tuple, value: Any) -> None:
    payload = valid_manifest()
    set_nested(payload, loc, value)
    reject(BatchManifest, payload)


def test_manifest_case_count_must_match_files() -> None:
    payload = valid_manifest()
    payload["case_count"] = payload["case_count"] + 1
    reject(BatchManifest, payload)


def test_manifest_empty_case_files_rejected() -> None:
    payload = valid_manifest()
    payload["case_files"] = []
    payload["case_count"] = 0
    reject(BatchManifest, payload)


def test_manifest_case_files_duplicate_rejected() -> None:
    payload = valid_manifest()
    payload["case_files"] = ["cases/demo_case_001.json", "cases/demo_case_001.json"]
    reject(BatchManifest, payload)


def test_manifest_case_files_unsorted_rejected() -> None:
    payload = valid_manifest()
    payload["case_files"] = ["cases/demo_case_002.json", "cases/demo_case_001.json"]
    reject(BatchManifest, payload)


def test_manifest_case_count_upper_bound_rejected() -> None:
    payload = valid_manifest()
    payload["case_count"] = 21
    payload["case_files"] = [f"cases/case_{i:02d}.json" for i in range(21)]
    reject(BatchManifest, payload)


def test_manifest_case_file_path_must_be_under_cases() -> None:
    payload = valid_manifest()
    payload["case_files"] = ["cases/demo_case_001.json", "data/other.json"]
    reject(BatchManifest, payload)


def test_manifest_acceptance_package_accepted() -> None:
    payload = valid_manifest()
    payload["package_type"] = "ACCEPTANCE"
    payload["batch_id"] = "acceptance_batch_v1"
    parsed = BatchManifest.model_validate(payload)
    assert parsed.package_type is PackageType.ACCEPTANCE


def test_evidence_text_items_required() -> None:
    payload = valid_case_input()
    payload["evidence"]["text_items"] = []
    reject(CaseInput, payload)


def test_duplicate_evidence_id_across_arrays_rejected() -> None:
    payload = valid_case_input()
    payload["evidence"]["behavior_items"][0]["evidence_id"] = "ev_text_001"
    reject(CaseInput, payload)


def test_duplicate_evidence_id_within_array_rejected() -> None:
    payload = valid_case_input()
    payload["evidence"]["text_items"][1]["evidence_id"] = "ev_text_001"
    reject(CaseInput, payload)


def test_evidence_ids_scoped_to_case() -> None:
    first = CaseInput.model_validate(valid_case_input())
    second = CaseInput.model_validate(valid_case_input())
    assert (
        first.evidence.text_items[0].evidence_id
        == second.evidence.text_items[0].evidence_id
    )


def test_evidence_empty_text_message_rejected() -> None:
    payload = valid_case_input()
    payload["evidence"]["text_items"][0]["text"] = ""
    reject(CaseInput, payload)


def test_provenance_source_refs_required() -> None:
    payload = valid_case_input()
    payload["provenance"]["source_refs"] = []
    reject(CaseInput, payload)


def test_evidence_source_ref_required() -> None:
    payload = valid_case_input()
    del payload["evidence"]["text_items"][0]["source_ref"]
    reject(CaseInput, payload)


@pytest.mark.parametrize(
    "relative_path",
    [
        "../secret.csv",
        "/etc/passwd",
        "C:/data/x.csv",
        "data\\with_backslash.csv",
        "a/../b.csv",
        "",
    ],
)
def test_source_ref_path_must_be_safe_relative(relative_path: str) -> None:
    payload = valid_case_input()
    payload["customer_value"]["source_ref"]["relative_path"] = relative_path
    reject(CaseInput, payload)


@pytest.mark.parametrize(
    ("loc", "value"),
    [
        (("case_id",), ""),
        (("case_id",), "x" * 129),
        (("case_id",), "含换行\n的ID"),
        (("customer", "customer_ref"), ""),
        (("evidence", "text_items", 0, "evidence_id"), ""),
        (("evidence", "text_items", 0, "content_hash"), "ABC"),
        (("evidence", "text_items", 0, "content_hash"), "A" * 64),
        (("evidence", "text_items", 0, "content_hash"), "g" + "a" * 63),
        (("provenance", "source_manifest_sha256"), "abc"),
    ],
)
def test_id_and_hash_constraints_rejected(loc: tuple, value: Any) -> None:
    payload = valid_case_input()
    set_nested(payload, loc, value)
    reject(CaseInput, payload)


def test_max_length_id_and_lowercase_sha_accepted() -> None:
    payload = valid_case_input()
    payload["case_id"] = "c" * 128
    payload["provenance"]["source_manifest_sha256"] = "a" * 64
    CaseInput.model_validate(payload)


def test_image_asset_path_must_be_safe_relative() -> None:
    for bad in ("../assets/x.jpg", "assets\\x.jpg", "C:/assets/x.jpg"):
        payload = valid_case_input()
        payload["evidence"]["image_items"][0]["asset_relative_path"] = bad
        reject(CaseInput, payload)


def test_image_items_may_be_empty() -> None:
    payload = valid_case_input()
    payload["evidence"]["image_items"] = []
    CaseInput.model_validate(payload)


def test_behavior_value_strings_stay_strings() -> None:
    item = valid_case_input()["evidence"]["behavior_items"][1]
    parsed = BehaviorEvidenceItem.model_validate(item)
    assert parsed.value == "delivered"
    assert isinstance(parsed.value, str)


def test_behavior_value_no_bool_coercion_from_string() -> None:
    item = valid_case_input()["evidence"]["behavior_items"][0]
    item["value"] = "true"
    parsed = BehaviorEvidenceItem.model_validate(item)
    assert parsed.value == "true"
    assert isinstance(parsed.value, str)


def test_behavior_value_numeric_string_parses_to_decimal() -> None:
    item = valid_case_input()["evidence"]["behavior_items"][3]
    parsed = BehaviorEvidenceItem.model_validate(item)
    assert isinstance(parsed.value, Decimal)
    assert parsed.value == Decimal("918.16")


def test_behavior_value_timestamp_string_parses_to_datetime() -> None:
    item = valid_case_input()["evidence"]["behavior_items"][2]
    parsed = BehaviorEvidenceItem.model_validate(item)
    assert isinstance(parsed.value, datetime)


def test_behavior_value_container_rejected() -> None:
    item = valid_case_input()["evidence"]["behavior_items"][0]
    item["value"] = {"nested": True}
    reject(BehaviorEvidenceItem, item)


def test_behavior_value_null_rejected() -> None:
    item = valid_case_input()["evidence"]["behavior_items"][0]
    item["value"] = None
    reject(BehaviorEvidenceItem, item)


def test_checksums_self_entry_rejected() -> None:
    payload = valid_checksums()
    payload["checksums.json"] = "a" * 64
    reject(Checksums, payload)


def test_checksums_path_must_be_safe_relative() -> None:
    for bad in ("../outside.json", "C:/data/x.json", "a\\b.json"):
        payload = valid_checksums()
        payload[bad] = "a" * 64
        reject(Checksums, payload)


def test_checksums_bad_hash_rejected() -> None:
    payload = valid_checksums()
    payload["cases/demo_case_001.json"] = "XYZ"
    reject(Checksums, payload)


def test_checksums_keys_normalized_sorted() -> None:
    parsed = Checksums.model_validate({"z.json": "a" * 64, "a.json": "b" * 64})
    assert list(parsed.root) == ["a.json", "z.json"]


def test_checksums_coverage_is_importer_concern() -> None:
    # 合同只约束路径与哈希格式；"必须覆盖 manifest/全部案例/全部图片"
    # 由导入器（M1-03/M1-04）负责，不在单文件 Schema 内强制。
    Checksums.model_validate({"cases/demo_case_001.json": "a" * 64})
