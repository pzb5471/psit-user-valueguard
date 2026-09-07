"""M2-01 合同验收：三个阶段结果合同（规格第 5.6、7.1、7.3、7.4 节）。

面向公开合同边界验证：严格类型、字段上限、冻结枚举、证据引用规则和
禁止额外字段。样例按规格第 9.4 节真实路径走 JSON 解析 + 严格校验；
不绑定内部实现与内部类名。
"""

from __future__ import annotations

import pytest
from analysis_samples import (
    attribution_result,
    cause,
    decision_package,
    emotion,
    image_observation,
    parse,
    perception_event,
    perception_result,
    strategy_action,
)
from pydantic import ValidationError

from app.contracts.analysis import (
    ACTION_CATALOG_VERSION,
    ActionType,
    AttributionResult,
    BusinessCause,
    DecisionPackage,
    Emotion,
    ImageAnalysisStatus,
    ImageTextRelation,
    InterventionLevel,
    PerceptionResult,
    ResolutionStatus,
    StatementBasis,
)

pytestmark = pytest.mark.task_m2_01


class TestPerceptionResult:
    def test_valid_sample_round_trips_through_json(self) -> None:
        result = parse(PerceptionResult, perception_result())
        restored = PerceptionResult.model_validate_json(result.model_dump_json())
        assert restored == result

    def test_rejects_extra_field(self) -> None:
        sample = perception_result(risk_answer="must not exist")
        with pytest.raises(ValidationError):
            parse(PerceptionResult, sample)

    def test_rejects_string_event_number_in_strict_mode(self) -> None:
        sample = perception_result(events=[perception_event(event_no="1")])
        with pytest.raises(ValidationError):
            parse(PerceptionResult, sample)

    def test_event_requires_supporting_evidence(self) -> None:
        sample = perception_result(events=[perception_event(evidence_ids=[])])
        with pytest.raises(ValidationError):
            parse(PerceptionResult, sample)

    def test_event_rejects_duplicate_evidence_ids(self) -> None:
        sample = perception_result(
            events=[perception_event(evidence_ids=["msg-001", "msg-001"])]
        )
        with pytest.raises(ValidationError):
            parse(PerceptionResult, sample)

    def test_event_number_must_be_positive(self) -> None:
        sample = perception_result(events=[perception_event(event_no=0)])
        with pytest.raises(ValidationError):
            parse(PerceptionResult, sample)

    def test_text_fields_have_upper_bound(self) -> None:
        sample = perception_result(events=[perception_event(summary="字" * 513)])
        with pytest.raises(ValidationError):
            parse(PerceptionResult, sample)

    def test_statement_basis_is_frozen_to_five_values(self) -> None:
        assert {member.value for member in StatementBasis} == {
            "CUSTOMER_CLAIMED",
            "SERVICE_AGENT_STATED_OR_PROMISED",
            "CUSTOMER_CONFIRMED",
            "IMAGE_DIRECT_OBSERVATION",
            "PROGRAM_DERIVED",
        }
        sample = perception_result(events=[perception_event(statement_basis="RUMOR")])
        with pytest.raises(ValidationError):
            parse(PerceptionResult, sample)

    def test_resolution_status_is_frozen_to_three_values(self) -> None:
        assert {member.value for member in ResolutionStatus} == {
            "RESOLVED",
            "UNRESOLVED",
            "UNCONFIRMABLE",
        }


class TestImageObservation:
    def test_valid_observation_is_accepted(self) -> None:
        result = parse(PerceptionResult, perception_result())
        assert result.image_observations[0].image_evidence_id == "img-001"

    def test_observable_facts_are_capped_at_three(self) -> None:
        sample = image_observation(observable_facts=["事实一", "事实二", "事实三", "事实四"])
        with pytest.raises(ValidationError):
            parse(PerceptionResult, perception_result(image_observations=[sample]))

    def test_relation_is_frozen_to_four_values(self) -> None:
        assert {member.value for member in ImageTextRelation} == {
            "MUTUALLY_SUPPORTS",
            "CONFLICTS_WITH",
            "SUPPLEMENTS",
            "UNDETERMINED",
        }

    def test_unknown_image_forbids_invented_facts_from_text(self) -> None:
        sample = image_observation(analysis_status="UNKNOWN", observable_facts=["凭文本想象的事实"])
        with pytest.raises(ValidationError):
            parse(PerceptionResult, perception_result(image_observations=[sample]))

    def test_analysis_status_is_frozen(self) -> None:
        assert {member.value for member in ImageAnalysisStatus} == {"ANALYZED", "UNKNOWN"}


class TestEmotion:
    def test_emotion_must_reference_customer_text_evidence(self) -> None:
        sample = emotion(evidence_ids=[])
        with pytest.raises(ValidationError):
            parse(PerceptionResult, perception_result(emotion=sample))

    def test_emotion_is_frozen_to_three_values(self) -> None:
        assert {member.value for member in Emotion} == {"CALM", "IMPATIENT", "UNDETERMINED"}


class TestAttributionResult:
    def test_valid_sample_round_trips_through_json(self) -> None:
        result = parse(AttributionResult, attribution_result())
        restored = AttributionResult.model_validate_json(result.model_dump_json())
        assert restored == result

    def test_accepts_at_most_one_alternative_cause(self) -> None:
        sample = attribution_result(alternative_cause=cause(category="SERVICE_COMMUNICATION"))
        result = parse(AttributionResult, sample)
        assert result.alternative_cause is not None
        assert result.alternative_cause.category == BusinessCause.SERVICE_COMMUNICATION

    def test_accepts_insufficient_evidence_fallback_with_no_evidence(self) -> None:
        sample = attribution_result(
            primary_cause=cause(category="INSUFFICIENT_EVIDENCE", evidence_ids=[])
        )
        result = parse(AttributionResult, sample)
        assert result.primary_cause.evidence_ids == []

    def test_rejects_cause_outside_six_reasons_plus_fallback(self) -> None:
        sample = attribution_result(primary_cause=cause(category="WEATHER"))
        with pytest.raises(ValidationError):
            parse(AttributionResult, sample)

    def test_rejects_extra_field(self) -> None:
        sample = attribution_result(probability=0.8)
        with pytest.raises(ValidationError):
            parse(AttributionResult, sample)


class TestDecisionPackage:
    def test_valid_sample_round_trips_through_json(self) -> None:
        package = parse(DecisionPackage, decision_package())
        restored = DecisionPackage.model_validate_json(package.model_dump_json())
        assert restored == package

    def test_actions_are_capped_at_three(self) -> None:
        sample = decision_package(actions=[strategy_action() for _ in range(4)])
        with pytest.raises(ValidationError):
            parse(DecisionPackage, sample)

    def test_at_least_one_action_is_required(self) -> None:
        sample = decision_package(actions=[])
        with pytest.raises(ValidationError):
            parse(DecisionPackage, sample)

    def test_communication_points_are_capped_at_three(self) -> None:
        sample = decision_package(communication_points=["一", "二", "三", "四"])
        with pytest.raises(ValidationError):
            parse(DecisionPackage, sample)

    def test_action_type_is_frozen_to_catalog_v1(self) -> None:
        assert {member.value for member in ActionType} == {
            "EVIDENCE_CHECK",
            "CUSTOMER_CONTACT",
            "FULFILLMENT_ESCALATION",
            "REPLACEMENT_RETURN_REFUND_CHECK",
            "APOLOGY_COMPENSATION_RETENTION_REQUEST",
            "NO_ACTION_MONITOR",
        }
        sample = decision_package(actions=[strategy_action(action_type="REFUND_NOW")])
        with pytest.raises(ValidationError):
            parse(DecisionPackage, sample)

    def test_intervention_level_reuses_frozen_states_contract(self) -> None:
        assert {member.value for member in InterventionLevel} == {
            "MUST_INTERVENE",
            "SHOULD_INTERVENE",
            "NO_IMMEDIATE_INTERVENTION",
        }
        sample = decision_package(intervention_level="NUKE_IT")
        with pytest.raises(ValidationError):
            parse(DecisionPackage, sample)

    def test_schema_version_is_pinned_to_v1(self) -> None:
        sample = decision_package(schema_version="v2")
        with pytest.raises(ValidationError):
            parse(DecisionPackage, sample)


def test_action_catalog_version_constant_matches_v1() -> None:
    assert ACTION_CATALOG_VERSION == "v1"
