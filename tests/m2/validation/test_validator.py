"""M2-04 验收：严格结果与证据校验器（规格第 5.6、7.4、9.2、9.4 节）。

面向公开接口验证 validate_stage_result：JSON 解析、Pydantic 严格校验、
case_id、证据归属与阶段允许集合、跨阶段引用、密封答案禁止内容、
动作目录与最低介入规则；错误可稳定区分可修复结构问题与不可重试污染。
允许证据集合作为参数由调用方传入（从 CaseInput 派生是 M3 装配职责）。
"""

from __future__ import annotations

from typing import Any

import pytest
from samples import (
    CASE_EVIDENCE_IDS,
    CASE_ID,
    CATALOG_ACTION_TYPES,
    PERCEPTION_CITED_IDS,
    attribution_raw,
    perception_raw,
    strategy_action_raw,
    strategy_raw,
    to_raw_json,
)

from app.contracts.analysis import AnalysisStage, InterventionLevel, PerceptionResult
from app.modules.analysis.validation import (
    AttributionValidationContext,
    PerceptionValidationContext,
    StrategyValidationContext,
    ValidationErrorCode,
    perception_cited_evidence_ids,
    validate_stage_result,
)

pytestmark = pytest.mark.task_m2_04


def perception_context() -> PerceptionValidationContext:
    return typed_perception_context()


def typed_perception_context() -> PerceptionValidationContext:
    return PerceptionValidationContext(
        case_id=CASE_ID,
        allowed_evidence_ids=CASE_EVIDENCE_IDS,
        customer_text_evidence_ids=frozenset({"msg-001"}),
        text_evidence_ids=frozenset({"msg-001", "msg-002"}),
        image_evidence_ids=frozenset({"img-001"}),
    )


def attribution_context() -> AttributionValidationContext:
    return AttributionValidationContext(
        case_id=CASE_ID,
        allowed_evidence_ids=CASE_EVIDENCE_IDS,
        upstream_cited_ids=PERCEPTION_CITED_IDS,
    )


def strategy_context(**overrides: Any) -> StrategyValidationContext:
    return StrategyValidationContext(
        case_id=CASE_ID,
        allowed_evidence_ids=CASE_EVIDENCE_IDS,
        upstream_cited_ids=PERCEPTION_CITED_IDS,
        catalog_action_types=overrides.get("catalog_action_types", CATALOG_ACTION_TYPES),
        severe_unresolved_present=overrides.get("severe_unresolved_present", True),
        evidence_conflict_or_insufficient=overrides.get(
            "evidence_conflict_or_insufficient", False
        ),
    )


def error_codes(outcome) -> set[ValidationErrorCode]:
    return {error.code for error in outcome.errors}


class TestHappyPath:
    """合法样例必须零错误通过，并返回解析后的严格结果。"""

    @pytest.mark.parametrize(
        ("stage", "raw", "context"),
        [
            (AnalysisStage.PERCEPTION, perception_raw(), perception_context()),
            (AnalysisStage.ATTRIBUTION, attribution_raw(), attribution_context()),
            (AnalysisStage.STRATEGY, strategy_raw(), strategy_context()),
        ],
    )
    def test_valid_stage_result_passes(self, stage, raw, context) -> None:
        outcome = validate_stage_result(stage, to_raw_json(raw), context)

        assert outcome.ok
        assert outcome.errors == ()
        assert outcome.result is not None
        assert outcome.result.case_id == CASE_ID


class TestParseAndSchema:
    """规格 9.4 步骤 1—2：JSON 解析与严格 Pydantic 校验，禁止额外字段。"""

    def test_broken_json_is_parse_failure(self) -> None:
        outcome = validate_stage_result(
            AnalysisStage.PERCEPTION, '{"case_id": ', perception_context()
        )

        assert not outcome.ok
        assert outcome.result is None
        assert error_codes(outcome) == {ValidationErrorCode.JSON_PARSE_FAILED}
        assert all(error.repairable for error in outcome.errors)

    def test_extra_field_rejected(self) -> None:
        raw = perception_raw()
        raw["confidence"] = 0.9

        outcome = validate_stage_result(
            AnalysisStage.PERCEPTION, to_raw_json(raw), perception_context()
        )

        assert not outcome.ok
        assert ValidationErrorCode.SCHEMA_VALIDATION_FAILED in error_codes(outcome)

    @pytest.mark.parametrize(
        "mutate",
        [
            lambda raw: raw["events"][0].__setitem__("statement_basis", "GUESSED"),
            lambda raw: raw["emotion"].__setitem__("value", "ANGRY"),
            lambda raw: raw["events"][0].__setitem__("event_no", 0),
        ],
    )
    def test_type_enum_and_range_violations_rejected(self, mutate) -> None:
        raw = perception_raw()
        mutate(raw)

        outcome = validate_stage_result(
            AnalysisStage.PERCEPTION, to_raw_json(raw), perception_context()
        )

        assert not outcome.ok
        assert ValidationErrorCode.SCHEMA_VALIDATION_FAILED in error_codes(outcome)
        assert all(error.repairable for error in outcome.errors)


class TestCaseId:
    """规格 9.4 步骤 3：case_id 必须与当前案例一致。"""

    def test_foreign_case_id_rejected(self) -> None:
        raw = attribution_raw(case_id="case-9999")

        outcome = validate_stage_result(
            AnalysisStage.ATTRIBUTION, to_raw_json(raw), attribution_context()
        )

        assert not outcome.ok
        assert ValidationErrorCode.CASE_ID_MISMATCH in error_codes(outcome)
        mismatch = next(
            error
            for error in outcome.errors
            if error.code is ValidationErrorCode.CASE_ID_MISMATCH
        )
        assert mismatch.field_path == "case_id"
        assert mismatch.repairable


class TestEvidenceScope:
    """规格 9.4 步骤 4—5：证据必须属于当前案例、当前阶段允许集合与跨阶段引用。"""

    @pytest.mark.parametrize(
        ("mutate", "field_path"),
        [
            (
                lambda raw: raw["events"][0].__setitem__("evidence_ids", ["msg-999"]),
                "events[0].evidence_ids",
            ),
            (
                lambda raw: raw["events"][0].__setitem__(
                    "conflict_evidence_ids", ["ord-404"]
                ),
                "events[0].conflict_evidence_ids",
            ),
            (
                lambda raw: raw["emotion"].__setitem__("evidence_ids", ["msg-777"]),
                "emotion.evidence_ids",
            ),
            (
                lambda raw: raw["image_observations"][0].__setitem__(
                    "image_evidence_id", "img-888"
                ),
                "image_observations[0].image_evidence_id",
            ),
            (lambda raw: raw["missing_evidence"].insert(0, "x"), None),
        ],
    )
    def test_perception_evidence_must_be_allowed(self, mutate, field_path) -> None:
        raw = perception_raw()
        if field_path is None:
            mutate(raw)
            outcome = validate_stage_result(
                AnalysisStage.PERCEPTION, to_raw_json(raw), perception_context()
            )
            assert outcome.ok
            return
        mutate(raw)
        outcome = validate_stage_result(
            AnalysisStage.PERCEPTION, to_raw_json(raw), perception_context()
        )

        assert not outcome.ok
        assert ValidationErrorCode.EVIDENCE_NOT_ALLOWED in error_codes(outcome)
        violation = next(
            error
            for error in outcome.errors
            if error.code is ValidationErrorCode.EVIDENCE_NOT_ALLOWED
        )
        assert violation.field_path == field_path

    def test_attribution_citing_case_evidence_not_cited_upstream(self) -> None:
        raw = attribution_raw()
        raw["primary_cause"]["evidence_ids"] = ["msg-002"]

        outcome = validate_stage_result(
            AnalysisStage.ATTRIBUTION, to_raw_json(raw), attribution_context()
        )

        assert not outcome.ok
        assert ValidationErrorCode.CROSS_STAGE_REFERENCE_INVALID in error_codes(outcome)

    @pytest.mark.parametrize(
        "mutate",
        [
            lambda raw: raw["emotion"].__setitem__("evidence_ids", ["msg-002"]),
            lambda raw: raw["image_observations"][0].__setitem__(
                "image_evidence_id", "msg-001"
            ),
            lambda raw: raw["image_observations"][0].__setitem__(
                "related_text_evidence_ids", ["img-001"]
            ),
        ],
    )
    def test_perception_references_must_match_field_evidence_type(self, mutate) -> None:
        raw = perception_raw()
        mutate(raw)

        outcome = validate_stage_result(
            AnalysisStage.PERCEPTION, to_raw_json(raw), typed_perception_context()
        )

        assert not outcome.ok
        assert ValidationErrorCode.EVIDENCE_NOT_ALLOWED in error_codes(outcome)

    def test_attribution_citing_fully_unknown_evidence(self) -> None:
        raw = attribution_raw()
        raw["primary_cause"]["evidence_ids"] = ["other-case:msg-001"]

        outcome = validate_stage_result(
            AnalysisStage.ATTRIBUTION, to_raw_json(raw), attribution_context()
        )

        assert not outcome.ok
        assert ValidationErrorCode.EVIDENCE_NOT_ALLOWED in error_codes(outcome)

    def test_strategy_citing_uncited_upstream_evidence(self) -> None:
        raw = strategy_raw()
        raw["actions"][0]["evidence_ids"] = ["ord-001"]

        outcome = validate_stage_result(
            AnalysisStage.STRATEGY, to_raw_json(raw), strategy_context()
        )

        assert not outcome.ok
        assert ValidationErrorCode.CROSS_STAGE_REFERENCE_INVALID in error_codes(outcome)


class TestForbiddenContent:
    """规格 9.4 步骤 6：密封答案等禁止内容出现在结果中必须失败且不可定向修复。"""

    @pytest.mark.parametrize(
        ("stage", "raw_factory", "context_factory"),
        [
            (AnalysisStage.PERCEPTION, lambda: perception_raw(), perception_context),
            (AnalysisStage.ATTRIBUTION, lambda: attribution_raw(), attribution_context),
            (AnalysisStage.STRATEGY, lambda: strategy_raw(), strategy_context),
        ],
    )
    def test_sealed_answer_token_in_text_rejected(
        self, stage, raw_factory, context_factory
    ) -> None:
        raw = raw_factory()
        if stage is AnalysisStage.PERCEPTION:
            raw["events"][0]["summary"] = "用户档案 user_profile 显示多次拒收。"
        elif stage is AnalysisStage.ATTRIBUTION:
            raw["risk_summary"] = "依据 database_gt 判定为物流原因。"
        else:
            raw["priority_reason"] = "key_answer 指向退款流程。"

        outcome = validate_stage_result(stage, to_raw_json(raw), context_factory())

        assert not outcome.ok
        assert ValidationErrorCode.FORBIDDEN_CONTENT in error_codes(outcome)
        forbidden = next(
            error
            for error in outcome.errors
            if error.code is ValidationErrorCode.FORBIDDEN_CONTENT
        )
        assert not forbidden.repairable


class TestActionCatalogAndFloor:
    """规格 9.4 步骤 7 与 7.4：目录外动作、数量与最低介入规则。"""

    def test_action_outside_catalog_rejected(self) -> None:
        """合同枚举是目录超集；调用方传入的目录版本可以比枚举更严格。"""
        raw = strategy_raw()
        restricted_catalog = CATALOG_ACTION_TYPES - {"EVIDENCE_CHECK"}

        outcome = validate_stage_result(
            AnalysisStage.STRATEGY,
            to_raw_json(raw),
            strategy_context(catalog_action_types=restricted_catalog),
        )

        assert not outcome.ok
        assert ValidationErrorCode.ACTION_CATALOG_VIOLATION in error_codes(outcome)

    def test_quantity_over_limit_caught_by_schema(self) -> None:
        raw = strategy_raw()
        raw["actions"] = [strategy_action_raw() for _ in range(4)]

        outcome = validate_stage_result(
            AnalysisStage.STRATEGY, to_raw_json(raw), strategy_context()
        )

        assert not outcome.ok
        assert ValidationErrorCode.SCHEMA_VALIDATION_FAILED in error_codes(outcome)

    def test_severe_unresolved_cannot_be_no_intervention(self) -> None:
        raw = strategy_raw(intervention_level="NO_IMMEDIATE_INTERVENTION")

        outcome = validate_stage_result(
            AnalysisStage.STRATEGY,
            to_raw_json(raw),
            strategy_context(severe_unresolved_present=True),
        )

        assert not outcome.ok
        assert ValidationErrorCode.MINIMUM_INTERVENTION_VIOLATION in error_codes(outcome)
        violation = next(
            error
            for error in outcome.errors
            if error.code is ValidationErrorCode.MINIMUM_INTERVENTION_VIOLATION
        )
        assert violation.field_path == "intervention_level"
        assert violation.repairable

    def test_conflict_or_insufficient_requires_at_least_should(self) -> None:
        raw = strategy_raw(intervention_level="NO_IMMEDIATE_INTERVENTION")

        outcome = validate_stage_result(
            AnalysisStage.STRATEGY,
            to_raw_json(raw),
            strategy_context(
                severe_unresolved_present=False, evidence_conflict_or_insufficient=True
            ),
        )

        assert not outcome.ok
        assert ValidationErrorCode.MINIMUM_INTERVENTION_VIOLATION in error_codes(outcome)

    def test_no_intervention_allowed_without_severe_or_conflict(self) -> None:
        raw = strategy_raw(
            intervention_level=InterventionLevel.NO_IMMEDIATE_INTERVENTION.value
        )

        outcome = validate_stage_result(
            AnalysisStage.STRATEGY,
            to_raw_json(raw),
            strategy_context(
                severe_unresolved_present=False, evidence_conflict_or_insufficient=False
            ),
        )

        assert outcome.ok


class TestPerceptionCitedDerivation:
    """归因阶段允许集合的派生规则：感知结果实际引用的全部证据编号。"""

    def test_collects_all_cited_ids_including_conflict_and_image(self) -> None:
        raw = perception_raw()
        raw["events"][0]["conflict_evidence_ids"] = ["msg-002"]
        perception = PerceptionResult.model_validate_json(to_raw_json(raw))

        cited = perception_cited_evidence_ids(perception)

        assert cited == frozenset({"msg-001", "msg-002", "img-001"})


class TestErrorStructure:
    """结构化错误必须携带阶段、字段路径与可序列化形式，供定向修复使用。"""

    def test_error_carries_stage_and_serializes(self) -> None:
        raw = attribution_raw(case_id="case-9999")

        outcome = validate_stage_result(
            AnalysisStage.ATTRIBUTION, to_raw_json(raw), attribution_context()
        )

        error = outcome.errors[0]
        assert error.stage is AnalysisStage.ATTRIBUTION
        payload = error.to_dict()
        assert payload["code"] == "CASE_ID_MISMATCH"
        assert payload["stage"] == "ATTRIBUTION"
        assert payload["field_path"]
        assert isinstance(payload["repairable"], bool)
