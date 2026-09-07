"""四种人工确认请求的判别联合校验（M3-03 自动验收；规格 12.3）。"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import TypeAdapter, ValidationError

from app.modules.application.api.contracts.reviews import ReviewRequest
from app.modules.application.api.contracts.views import (
    ACTION_TYPE_OPTIONS,
    INTERVENTION_LEVEL_OPTIONS,
    build_review_options,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
adapter = TypeAdapter(ReviewRequest)


def base_payload(outcome: str) -> dict[str, object]:
    return {
        "submission_id": str(uuid4()),
        "review_token": "opaque-token",
        "outcome": outcome,
    }


def judgment_payload(outcome: str) -> dict[str, object]:
    payload = base_payload(outcome)
    payload.update(
        {
            "final_intervention_level": "MUST_INTERVENE",
            "final_cause": "LOGISTICS_FULFILLMENT",
            "final_actions": ["CUSTOMER_CONTACT", "EVIDENCE_CHECK"],
            "review_reason": "物流时效异常，需人工介入",
        }
    )
    return payload


def test_four_outcomes_parse_into_their_variants() -> None:
    approved = adapter.validate_python(base_payload("APPROVED"))
    assert approved.outcome == "APPROVED"

    modified = adapter.validate_python(judgment_payload("MODIFIED_AND_APPROVED"))
    assert modified.final_intervention_level == "MUST_INTERVENE"
    assert modified.final_actions == ["CUSTOMER_CONTACT", "EVIDENCE_CHECK"]

    rejected = adapter.validate_python(judgment_payload("REJECTED_WITH_JUDGMENT"))
    assert rejected.review_reason

    insufficient = adapter.validate_python(
        {**base_payload("INSUFFICIENT_EVIDENCE"), "review_reason": "缺少物流签收凭证"}
    )
    assert insufficient.review_reason == "缺少物流签收凭证"


def test_approved_rejects_extra_human_result() -> None:
    payload = {**base_payload("APPROVED"), "final_cause": "OTHER"}
    with pytest.raises(ValidationError):
        adapter.validate_python(payload)


def test_insufficient_evidence_rejects_certain_cause_and_actions() -> None:
    payload = judgment_payload("INSUFFICIENT_EVIDENCE")
    with pytest.raises(ValidationError):
        adapter.validate_python(payload)


def test_modified_requires_reason_and_full_judgment() -> None:
    missing_reason = judgment_payload("MODIFIED_AND_APPROVED")
    del missing_reason["review_reason"]
    with pytest.raises(ValidationError):
        adapter.validate_python(missing_reason)

    missing_actions = judgment_payload("MODIFIED_AND_APPROVED")
    del missing_actions["final_actions"]
    with pytest.raises(ValidationError):
        adapter.validate_python(missing_actions)


def test_out_of_catalog_values_are_rejected() -> None:
    payload = judgment_payload("MODIFIED_AND_APPROVED")
    payload["final_actions"] = ["FREE_REFUND_EVERYONE"]
    with pytest.raises(ValidationError):
        adapter.validate_python(payload)

    payload = judgment_payload("REJECTED_WITH_JUDGMENT")
    payload["final_cause"] = "INSUFFICIENT_EVIDENCE"
    with pytest.raises(ValidationError):
        adapter.validate_python(payload)


def test_unknown_outcome_is_rejected() -> None:
    with pytest.raises(ValidationError):
        adapter.validate_python(base_payload("APPROVED_WITH_VIBES"))


def test_action_options_match_action_catalog_file() -> None:
    """review_options 是动作目录的只读投影；两处不得漂移（规格 7.3/12.2）。"""
    catalog = json.loads(
        (REPO_ROOT / "config" / "action_catalog.v1.json").read_text(encoding="utf-8")
    )
    catalog_actions = {item["action_type"]: item["description"] for item in catalog["actions"]}
    options = {item.value: item.label for item in ACTION_TYPE_OPTIONS}
    assert options == catalog_actions
    assert build_review_options().action_catalog_version == "action_catalog.v1"


def test_intervention_options_match_shared_contract_labels() -> None:
    from app.contracts.analysis import InterventionLevel

    options = {item.value: item.label for item in INTERVENTION_LEVEL_OPTIONS}
    assert options == dict(InterventionLevel.LABELS)
