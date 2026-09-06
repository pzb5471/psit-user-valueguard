"""M2-07 验收：策略阶段输入构造器与执行器（规格第 7.3、7.4、9.2、9.3 节）。

面向公开接口验证：输入构造器只携带两阶段结果、高价值结论、动作目录与
获准证据（不重发原图、完整对话或 RFM 过程）；执行器调用唯一模型客户端、
按 M2-04 上下文严格校验，并以程序底线调整介入等级（不增加模型请求）。
"""

from __future__ import annotations

import json

import pytest
from strategy_samples import (
    CASE_EVIDENCE_IDS,
    CASE_ID,
    CATALOG_ACTIONS,
    CATALOG_VERSION,
    HIGH_VALUE_CONCLUSION,
    attribution_stage_input,
    attribution_valid_json,
    no_intervention_json,
    strategy_json,
)

from app.contracts.analysis import (
    AnalysisErrorCode,
    AnalysisStage,
    AttributionFallbackCause,
    AttributionResult,
    DecisionPackage,
    InterventionLevel,
    PerceptionResult,
)
from app.modules.analysis.client import GlmClientError, GlmResponse, ScriptedGlmClient
from app.modules.analysis.prompts import load_stage_prompt
from app.modules.analysis.strategy import (
    ActionCatalogView,
    StrategyStageInput,
    build_strategy_request,
    derive_intervention_floor,
    run_strategy_stage,
)

pytestmark = pytest.mark.task_m2_07


def loaded_attribution() -> AttributionResult:
    return AttributionResult.model_validate_json(attribution_valid_json())


def strategy_input() -> StrategyStageInput:
    source = attribution_stage_input()
    return StrategyStageInput(
        perception=source.perception,
        attribution=loaded_attribution(),
        high_value_conclusion=HIGH_VALUE_CONCLUSION,
        action_catalog=ActionCatalogView(
            catalog_version=CATALOG_VERSION, actions=CATALOG_ACTIONS
        ),
        evidence_content=source.evidence_content,
    )


class TestInputBuilder:
    """策略输入最小权限：两阶段结果、高价值结论、目录与获准证据。"""

    def test_request_carries_strategy_prompt(self) -> None:
        request = build_strategy_request(
            strategy_input(), prompt=load_stage_prompt(AnalysisStage.STRATEGY)
        )

        assert request.stage is AnalysisStage.STRATEGY
        assert request.system_prompt == load_stage_prompt(
            AnalysisStage.STRATEGY
        ).rendered_text
        assert request.images == ()

    def test_user_content_contains_upstream_results_and_conclusion(self) -> None:
        request = build_strategy_request(
            strategy_input(), prompt=load_stage_prompt(AnalysisStage.STRATEGY)
        )

        assert '"statement_basis": "CUSTOMER_CLAIMED"' in request.user_content
        assert '"category": "PRODUCT_ISSUE"' in request.user_content
        assert "is_high_value: True" in request.user_content
        assert HIGH_VALUE_CONCLUSION.decision_reason in request.user_content

    def test_user_content_lists_catalog_without_extra_actions(self) -> None:
        request = build_strategy_request(
            strategy_input(), prompt=load_stage_prompt(AnalysisStage.STRATEGY)
        )

        for action in CATALOG_ACTIONS:
            assert action.action_type in request.user_content
        assert f"catalog_version: {CATALOG_VERSION}" in request.user_content
        assert "REFUND_NOW" not in request.user_content

    def test_user_content_contains_only_cited_evidence(self) -> None:
        request = build_strategy_request(
            strategy_input(), prompt=load_stage_prompt(AnalysisStage.STRATEGY)
        )

        assert "[msg-002]" in request.user_content
        assert "[ord-001]" not in request.user_content

    def test_rfm_values_never_enter_request(self) -> None:
        """RFM 数值与计算过程是策略阶段禁止读取内容。"""
        request = build_strategy_request(
            strategy_input(), prompt=load_stage_prompt(AnalysisStage.STRATEGY)
        )

        for token in ("r_p75", "m_p80", "recency_days", "frequency_orders"):
            assert token not in request.user_content

    def test_missing_cited_content_fails_fast(self) -> None:
        source = attribution_stage_input()
        content = {
            key: value
            for key, value in source.evidence_content.items()
            if key != "msg-002"
        }

        with pytest.raises(ValueError, match="msg-002"):
            build_strategy_request(
                StrategyStageInput(
                    perception=source.perception,
                    attribution=loaded_attribution(),
                    high_value_conclusion=HIGH_VALUE_CONCLUSION,
                    action_catalog=ActionCatalogView(
                        catalog_version=CATALOG_VERSION, actions=CATALOG_ACTIONS
                    ),
                    evidence_content=content,
                ),
                prompt=load_stage_prompt(AnalysisStage.STRATEGY),
            )


class TestInterventionFloorDerivation:
    """程序底线输入派生：严重未解决问题与证据冲突/不足。"""

    def test_severe_unresolved_product_issue_is_detected(self) -> None:
        source = attribution_stage_input()

        severe, conflict = derive_intervention_floor(
            source.perception, loaded_attribution()
        )

        assert severe is True
        assert conflict is False

    def test_conflicting_events_trigger_conflict_flag(self) -> None:
        source = attribution_stage_input()
        raw = source.perception.model_dump(mode="python")
        raw["events"][0]["conflict_evidence_ids"] = ["msg-002"]
        perception = PerceptionResult.model_validate_json(
            json.dumps(raw, ensure_ascii=False)
        )

        severe, conflict = derive_intervention_floor(
            perception, loaded_attribution()
        )

        assert severe is True
        assert conflict is True

    def test_insufficient_evidence_cause_triggers_conflict_flag(self) -> None:
        source = attribution_stage_input()
        attribution = AttributionResult.model_validate_json(attribution_valid_json())
        adjusted = attribution.model_copy(
            update={
                "primary_cause": attribution.primary_cause.model_copy(
                    update={"category": AttributionFallbackCause.INSUFFICIENT_EVIDENCE}
                )
            }
        )

        _, conflict = derive_intervention_floor(source.perception, adjusted)

        assert conflict is True

    def test_resolved_case_without_risk_allows_no_intervention(self) -> None:
        source = attribution_stage_input()
        raw = source.perception.model_dump(mode="python")
        for event in raw["events"]:
            event["resolution"] = "RESOLVED"
        perception = PerceptionResult.model_validate_json(
            json.dumps(raw, ensure_ascii=False)
        )
        attribution = loaded_attribution().model_copy(
            update={
                "primary_cause": loaded_attribution().primary_cause.model_copy(
                    update={"category": "SERVICE_COMMUNICATION"}
                )
            }
        )

        severe, conflict = derive_intervention_floor(perception, attribution)

        assert severe is False
        assert conflict is False


class TestExecutor:
    """执行器：严格校验 + 程序底线调整（不增加模型请求）。"""

    def test_valid_must_intervene_output_passes(self) -> None:
        client = ScriptedGlmClient([GlmResponse(content=strategy_json())])

        result = run_strategy_stage(
            strategy_input(),
            model_client=client,
            case_id=CASE_ID,
            allowed_evidence_ids=CASE_EVIDENCE_IDS,
        )

        assert result.model_error is None
        assert result.outcome is not None and result.outcome.ok
        assert result.floor_adjusted is False
        assert len(result.attempts) == 1

    def test_action_outside_catalog_returns_repairable_error(self) -> None:
        """合同枚举是目录超集；目录版本收窄时，目录外动作仍被拦截。"""
        restricted_catalog = ActionCatalogView(
            catalog_version=CATALOG_VERSION,
            actions=tuple(
                action
                for action in CATALOG_ACTIONS
                if action.action_type != "EVIDENCE_CHECK"
            ),
        )
        source = attribution_stage_input()
        restricted_input = StrategyStageInput(
            perception=source.perception,
            attribution=loaded_attribution(),
            high_value_conclusion=HIGH_VALUE_CONCLUSION,
            action_catalog=restricted_catalog,
            evidence_content=source.evidence_content,
        )
        client = ScriptedGlmClient([GlmResponse(content=strategy_json())])

        result = run_strategy_stage(
            restricted_input,
            model_client=client,
            case_id=CASE_ID,
            allowed_evidence_ids=CASE_EVIDENCE_IDS,
        )

        assert result.outcome is not None and not result.outcome.ok
        codes = {error.code.value for error in result.outcome.errors}
        assert "ACTION_CATALOG_VIOLATION" in codes

    def test_no_intervention_with_severe_issue_is_program_adjusted(self) -> None:
        client = ScriptedGlmClient([GlmResponse(content=no_intervention_json())])

        result = run_strategy_stage(
            strategy_input(),
            model_client=client,
            case_id=CASE_ID,
            allowed_evidence_ids=CASE_EVIDENCE_IDS,
        )

        assert result.outcome is not None and result.outcome.ok
        assert result.floor_adjusted is True
        decision = result.outcome.result
        assert isinstance(decision, DecisionPackage)
        assert decision.intervention_level is InterventionLevel.SHOULD_INTERVENE
        assert decision.caution_note is not None
        assert "人工核验" in decision.caution_note
        assert len(result.attempts) == 1

    def test_adjusted_result_still_cites_valid_evidence(self) -> None:
        raw = json.loads(no_intervention_json())
        raw["actions"][0]["evidence_ids"] = ["ord-404"]
        client = ScriptedGlmClient([GlmResponse(content=json.dumps(raw, ensure_ascii=False))])

        result = run_strategy_stage(
            strategy_input(),
            model_client=client,
            case_id=CASE_ID,
            allowed_evidence_ids=CASE_EVIDENCE_IDS,
        )

        assert result.outcome is not None and not result.outcome.ok
        codes = {error.code.value for error in result.outcome.errors}
        assert "MINIMUM_INTERVENTION_VIOLATION" not in codes
        assert "EVIDENCE_NOT_ALLOWED" in codes

    def test_provider_error_recorded_for_engine(self) -> None:
        client = ScriptedGlmClient(
            [GlmClientError(AnalysisErrorCode.MODEL_RATE_LIMITED, "限流")]
        )

        result = run_strategy_stage(
            strategy_input(),
            model_client=client,
            case_id=CASE_ID,
            allowed_evidence_ids=CASE_EVIDENCE_IDS,
        )

        assert result.outcome is None
        assert result.model_error is not None
        assert result.model_error.error_code is AnalysisErrorCode.MODEL_RATE_LIMITED
