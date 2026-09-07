"""业务 DTO 字段白名单与技术字段禁入（M3-03 自动验收；规格 12.2）。"""

from __future__ import annotations

from datetime import UTC, datetime

from app.contracts.states import CaseStatus
from app.modules.application.api.contracts.views import (
    BatchListView,
    BatchWorkspaceView,
    CaseDetailView,
    CaseQueueItemView,
    CaseQueueView,
    ReviewResultView,
    build_review_options,
)

FIELD_WHITELISTS: dict[type, set[str]] = {
    BatchWorkspaceView: {
        "batch_id",
        "source_filename",
        "is_mock",
        "status",
        "case_count",
        "evidence_count",
        "analysis_succeeded_count",
        "error_count",
        "imported_at",
        "can_start_analysis",
        "analysis_unavailable_message",
    },
    BatchListView: {"items", "total"},
    CaseQueueItemView: {
        "case_id",
        "customer_display_id",
        "is_high_value",
        "risk_summary",
        "intervention_level",
        "priority_reason",
        "status",
        "has_evidence_conflict",
        "has_insufficient_evidence",
        "has_modality_failure",
    },
    CaseQueueView: {"items", "total"},
    CaseDetailView: {
        "batch_id",
        "case_id",
        "customer_display_id",
        "is_high_value",
        "customer_value_summary",
        "status",
        "intervention_level",
        "risk_summary",
        "primary_cause",
        "actions",
        "communication_points",
        "uncertainty",
        "missing_evidence",
        "cited_evidence",
        "is_mock",
        "review_result",
        "processing_error",
        "can_rerun",
        "can_review",
        "review_token",
        "review_options",
    },
    ReviewResultView: {
        "outcome",
        "final_intervention_level",
        "final_cause",
        "final_actions",
        "execution_note",
        "review_reason",
        "created_at",
    },
}

#: 规格 12.2 结尾禁止出现在业务 DTO 中的技术字段（review_token 是唯一例外）。
FORBIDDEN_TECH_FIELDS = {
    "batch_run_id",
    "case_run_id",
    "run_id",
    "data_version",
    "schema_version",
    "prompt",
    "prompt_version",
    "model_name",
    "model_params",
    "total_tokens",
    "content_hash",
    "file_path",
    "raw_json",
    "rfm",
    "database_id",
}


def test_view_fields_match_spec_whitelists() -> None:
    for model, expected in FIELD_WHITELISTS.items():
        actual = set(model.model_fields)
        assert actual == expected, f"{model.__name__} 字段与规格 12.2 不一致"


def test_no_technical_fields_leak_into_views() -> None:
    for model in FIELD_WHITELISTS:
        leaked = set(model.model_fields) & FORBIDDEN_TECH_FIELDS
        assert not leaked, f"{model.__name__} 泄漏技术字段：{leaked}"


def test_optional_fields_omit_instead_of_null() -> None:
    now = datetime(2026, 9, 7, tzinfo=UTC)
    detail = CaseDetailView(
        batch_id="b-1",
        case_id="c-1",
        customer_display_id="客户-0001",
        is_high_value=True,
        customer_value_summary="高价值客户",
        status=CaseStatus.PENDING_ANALYSIS,
        is_mock=True,
        can_rerun=False,
        can_review=False,
    )
    dumped = detail.model_dump(exclude_none=True)
    assert None not in dumped.values()
    assert "review_token" not in dumped
    assert "review_options" not in dumped
    assert "processing_error" not in dumped

    result = ReviewResultView(outcome="APPROVED", created_at=now)
    assert "final_cause" not in result.model_dump(exclude_none=True)


def test_review_options_projection_is_frozen() -> None:
    options = build_review_options()
    levels = [item.value for item in options.intervention_levels]
    assert levels == [
        "MUST_INTERVENE",
        "SHOULD_INTERVENE",
        "NO_IMMEDIATE_INTERVENTION",
    ]
    causes = [item.value for item in options.cause_categories]
    assert causes == [
        "LOGISTICS_FULFILLMENT",
        "PRODUCT_ISSUE",
        "RETURN_REFUND",
        "SERVICE_COMMUNICATION",
        "PRICE_OR_BENEFIT",
        "OTHER",
    ]
    assert "INSUFFICIENT_EVIDENCE" not in causes
    assert options.action_catalog_version == "action_catalog.v1"
    assert len(options.action_types) == 6
    assert len(options.intervention_levels) == 3
