"""M2-06 验收：归因阶段输入构造器与执行器（规格第 7.1、7.2、9.2、9.3 节）。

面向公开接口验证：输入构造器只携带感知结果与获准引用证据（不重发原图、
不带高价值结论、RFM 或动作目录）；执行器调用唯一模型客户端、走 M2-04
严格校验，主要原因与最多一个备选原因、证据不足兜底、越权与跨阶段引用
全部按验收边界覆盖。
"""

from __future__ import annotations

import json

import pytest
from attribution_samples import (
    CASE_EVIDENCE_IDS,
    CASE_ID,
    EVIDENCE_CONTENT,
    attribution_json,
    insufficient_evidence_json,
    loaded_perception,
)

from app.contracts.analysis import AnalysisErrorCode, AnalysisStage
from app.modules.analysis.attribution import (
    AttributionStageInput,
    build_attribution_request,
    run_attribution_stage,
)
from app.modules.analysis.client import (
    GlmClientError,
    GlmResponse,
    ScriptedGlmClient,
)
from app.modules.analysis.prompts import load_stage_prompt

pytestmark = pytest.mark.task_m2_06


def stage_input(**content_overrides) -> AttributionStageInput:
    content = dict(EVIDENCE_CONTENT)
    content.update(content_overrides)
    return AttributionStageInput(
        perception=loaded_perception(), evidence_content=content
    )


class TestInputBuilder:
    """归因输入最小权限：只带感知结果与获准引用证据，不重发原图。"""

    def test_request_carries_stage_prompt_and_version(self) -> None:
        prompt = load_stage_prompt(AnalysisStage.ATTRIBUTION)
        request = build_attribution_request(stage_input(), prompt=prompt)

        assert request.stage is AnalysisStage.ATTRIBUTION
        assert request.prompt_version == prompt.version
        assert request.system_prompt == prompt.rendered_text
        assert "{{RESPONSE_JSON_SCHEMA}}" not in request.system_prompt

    def test_user_content_contains_perception_and_cited_evidence_in_order(self) -> None:
        request = build_attribution_request(
            stage_input(), prompt=load_stage_prompt(AnalysisStage.ATTRIBUTION)
        )

        assert '"statement_basis": "CUSTOMER_CLAIMED"' in request.user_content
        assert '"image_observations"' in request.user_content
        assert "搅拌机底座有烧焦痕迹。" in request.user_content
        msg_position = request.user_content.index("[msg-001]")
        msg_two_position = request.user_content.index("[msg-002]")
        assert msg_position < msg_two_position
        assert EVIDENCE_CONTENT["msg-001"] in request.user_content
        assert EVIDENCE_CONTENT["msg-002"] in request.user_content

    def test_optional_fields_are_omitted_not_null(self) -> None:
        request = build_attribution_request(
            stage_input(), prompt=load_stage_prompt(AnalysisStage.ATTRIBUTION)
        )

        assert "null" not in request.user_content

    def test_image_content_line_is_not_resent(self) -> None:
        """图片可观察内容已随感知 JSON 提供，不重发图片内容行或原图。"""
        request = build_attribution_request(
            stage_input(), prompt=load_stage_prompt(AnalysisStage.ATTRIBUTION)
        )

        assert EVIDENCE_CONTENT["img-001"] not in request.user_content

    def test_uncited_evidence_content_is_excluded(self) -> None:
        """输入越权防线：感知未引用的证据内容不得进入归因请求。"""
        content = dict(EVIDENCE_CONTENT)
        content["ord-001"] = "（ORDER）未被感知引用的订单事实。"

        request = build_attribution_request(
            AttributionStageInput(perception=loaded_perception(), evidence_content=content),
            prompt=load_stage_prompt(AnalysisStage.ATTRIBUTION),
        )

        assert "[ord-001]" not in request.user_content

    def test_original_images_are_not_resent(self) -> None:
        request = build_attribution_request(
            stage_input(), prompt=load_stage_prompt(AnalysisStage.ATTRIBUTION)
        )

        assert request.images == ()

    def test_missing_cited_text_content_fails_fast(self) -> None:
        content = {key: value for key, value in EVIDENCE_CONTENT.items() if key != "msg-001"}

        with pytest.raises(ValueError, match="msg-001"):
            build_attribution_request(
                AttributionStageInput(perception=loaded_perception(), evidence_content=content),
                prompt=load_stage_prompt(AnalysisStage.ATTRIBUTION),
            )

    def test_image_ids_do_not_require_content_mapping(self) -> None:
        content = {key: value for key, value in EVIDENCE_CONTENT.items() if key != "img-001"}

        request = build_attribution_request(
            AttributionStageInput(perception=loaded_perception(), evidence_content=content),
            prompt=load_stage_prompt(AnalysisStage.ATTRIBUTION),
        )

        assert request.stage is AnalysisStage.ATTRIBUTION


class TestExecutor:
    """执行器：调用唯一模型客户端并按 M2-04 上下文严格校验。"""

    def test_valid_model_output_passes_with_one_attempt(self) -> None:
        client = ScriptedGlmClient([GlmResponse(content=attribution_json())])

        result = run_attribution_stage(
            stage_input(),
            model_client=client,
            case_id=CASE_ID,
            allowed_evidence_ids=CASE_EVIDENCE_IDS,
        )

        assert result.model_error is None
        assert result.outcome is not None and result.outcome.ok
        assert len(result.attempts) == 1
        assert result.attempts[0].response is not None
        assert result.attempts[0].request_manifest is not None
        assert len(client.requests) == 1

    def test_insufficient_evidence_fallback_is_valid(self) -> None:
        client = ScriptedGlmClient([GlmResponse(content=insufficient_evidence_json())])

        result = run_attribution_stage(
            stage_input(),
            model_client=client,
            case_id=CASE_ID,
            allowed_evidence_ids=CASE_EVIDENCE_IDS,
        )

        assert result.outcome is not None and result.outcome.ok

    def test_alternative_cause_is_allowed_but_optional(self) -> None:
        single_cause = json.loads(attribution_json())
        del single_cause["alternative_cause"]
        client = ScriptedGlmClient(
            [
                GlmResponse(content=json.dumps(single_cause, ensure_ascii=False)),
                GlmResponse(content=attribution_json()),
            ]
        )

        first = run_attribution_stage(
            stage_input(),
            model_client=client,
            case_id=CASE_ID,
            allowed_evidence_ids=CASE_EVIDENCE_IDS,
        )
        second = run_attribution_stage(
            stage_input(),
            model_client=client,
            case_id=CASE_ID,
            allowed_evidence_ids=CASE_EVIDENCE_IDS,
        )

        assert first.outcome is not None and first.outcome.ok
        assert second.outcome is not None and second.outcome.ok

    def test_model_json_with_cross_stage_violation_returns_repairable_errors(self) -> None:
        """越权引用感知未引用的证据：结构化错误返回引擎做定向修复。"""
        raw = json.loads(attribution_json())
        raw["primary_cause"]["evidence_ids"] = ["ord-001"]
        client = ScriptedGlmClient([GlmResponse(content=json.dumps(raw, ensure_ascii=False))])

        result = run_attribution_stage(
            stage_input(),
            model_client=client,
            case_id=CASE_ID,
            allowed_evidence_ids=CASE_EVIDENCE_IDS,
        )

        assert result.outcome is not None and not result.outcome.ok
        codes = {error.code for error in result.outcome.errors}
        assert "CROSS_STAGE_REFERENCE_INVALID" in {code.value for code in codes}

    def test_provider_error_is_recorded_for_engine_retry(self) -> None:
        client = ScriptedGlmClient(
            [GlmClientError(AnalysisErrorCode.MODEL_TIMEOUT, "读取超时")]
        )

        result = run_attribution_stage(
            stage_input(),
            model_client=client,
            case_id=CASE_ID,
            allowed_evidence_ids=CASE_EVIDENCE_IDS,
        )

        assert result.outcome is None
        assert result.model_error is not None
        assert result.model_error.error_code is AnalysisErrorCode.MODEL_TIMEOUT
        assert len(result.attempts) == 1
        assert result.attempts[0].response is None

    def test_request_manifest_is_deterministic_and_promptless(self) -> None:
        prompt = load_stage_prompt(AnalysisStage.ATTRIBUTION)
        first = run_attribution_stage(
            stage_input(),
            model_client=ScriptedGlmClient([GlmResponse(content=attribution_json())]),
            case_id=CASE_ID,
            allowed_evidence_ids=CASE_EVIDENCE_IDS,
        )
        second = run_attribution_stage(
            stage_input(),
            model_client=ScriptedGlmClient([GlmResponse(content=attribution_json())]),
            case_id=CASE_ID,
            allowed_evidence_ids=CASE_EVIDENCE_IDS,
        )

        manifest = first.attempts[0].request_manifest
        assert manifest == second.attempts[0].request_manifest
        assert "system_prompt_sha256" in manifest
        assert prompt.rendered_text not in json.dumps(manifest)
        assert EVIDENCE_CONTENT["msg-001"] not in json.dumps(manifest)
