"""M3-07 人工确认测试：四种命令、禁用字段、旧 Token、已完成冲突、幂等。"""

from __future__ import annotations

from uuid import uuid4

from review_fakes import (
    completed_error,
    make_result,
    stale_result_error,
    validation_error,
)

BASE = {
    "submission_id": str(uuid4()),
    "review_token": "opaque-token",
}


def _approved():
    return {**BASE, "outcome": "APPROVED"}


def _modified(**extra):
    return {
        **BASE,
        "outcome": "MODIFIED_AND_APPROVED",
        "final_intervention_level": "MUST_INTERVENE",
        "final_cause": "LOGISTICS_FULFILLMENT",
        "final_actions": ["CUSTOMER_CONTACT", "EVIDENCE_CHECK"],
        "review_reason": "物流时效异常，需人工介入",
        **extra,
    }


def _rejected():
    return {
        **BASE,
        "outcome": "REJECTED_WITH_JUDGMENT",
        "final_intervention_level": "SHOULD_INTERVENE",
        "final_cause": "SERVICE_COMMUNICATION",
        "final_actions": ["CUSTOMER_CONTACT"],
        "review_reason": "沟通未果，需再次介入",
    }


def _insufficient():
    return {**BASE, "outcome": "INSUFFICIENT_EVIDENCE", "review_reason": "缺少物流签收凭证"}


def test_approved_review_201(app, review_store, service) -> None:
    review_store.result = make_result("APPROVED")
    response = app.post("/api/v1/batches/b1/cases/c1/reviews", json=_approved())
    assert response.status_code == 201
    assert review_store.submissions[0]["case_run_id"] == 1


def test_four_outcomes_submitted(app, review_store, service) -> None:
    for body in (_approved(), _modified(), _rejected(), _insufficient()):
        review_store.result = make_result(body["outcome"])
        response = app.post("/api/v1/batches/b1/cases/c1/reviews", json=body)
        assert response.status_code == 201, body["outcome"]
    outcomes = [s["payload"].outcome for s in review_store.submissions]
    assert outcomes == [
        "APPROVED",
        "MODIFIED_AND_APPROVED",
        "REJECTED_WITH_JUDGMENT",
        "INSUFFICIENT_EVIDENCE",
    ]


def test_modified_payload_shape(app, review_store, service) -> None:
    review_store.result = make_result("MODIFIED_AND_APPROVED")
    app.post("/api/v1/batches/b1/cases/c1/reviews", json=_modified())
    payload = review_store.submissions[0]["payload"]
    assert payload.final_cause == {"cause_category": "LOGISTICS_FULFILLMENT"}
    assert payload.final_actions == [
        {"action_type": "CUSTOMER_CONTACT"},
        {"action_type": "EVIDENCE_CHECK"},
    ]


def test_stale_token_409(app, review_store, service) -> None:
    review_store.error = stale_result_error()
    response = app.post("/api/v1/batches/b1/cases/c1/reviews", json=_approved())
    assert response.status_code == 409
    assert response.json()["code"] == "STALE_CASE_RESULT"


def test_completed_conflict_409(app, review_store, service) -> None:
    review_store.error = completed_error()
    response = app.post("/api/v1/batches/b1/cases/c1/reviews", json=_approved())
    assert response.status_code == 409
    assert response.json()["code"] == "CASE_ALREADY_COMPLETED"


def test_invalid_payload_422(app, review_store, service) -> None:
    review_store.error = validation_error()
    response = app.post("/api/v1/batches/b1/cases/c1/reviews", json=_modified())
    assert response.status_code == 422
    assert response.json()["code"] == "REQUEST_VALIDATION_FAILED"


def test_missing_case_run_404(app, query, service) -> None:
    query.current_case_run_id = None
    response = app.post("/api/v1/batches/b1/cases/c1/reviews", json=_approved())
    assert response.status_code == 404
    assert response.json()["code"] == "RESOURCE_NOT_FOUND"


def test_result_maps_to_api_view(app, review_store, service) -> None:
    review_store.result = make_result(
        "MODIFIED_AND_APPROVED",
        final_intervention_level="MUST_INTERVENE",
        cause_category="LOGISTICS_FULFILLMENT",
        action_types=["CUSTOMER_CONTACT"],
    )
    response = app.post("/api/v1/batches/b1/cases/c1/reviews", json=_modified())
    body = response.json()
    assert body["outcome"] == "MODIFIED_AND_APPROVED"
    assert body["final_intervention_level"] == "MUST_INTERVENE"
    assert body["final_cause"]["category"] == "LOGISTICS_FULFILLMENT"
    assert body["final_actions"][0]["action_type"] == "CUSTOMER_CONTACT"
