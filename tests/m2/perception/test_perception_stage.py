"""M2-05 验收：感知阶段输入构造器与执行器（规格第 7.1、9.2、9.3 节）。

面向公开接口验证：输入构造器只携带当前案例脱敏对话、图片、已核验订单与
履约事实（过滤付款金额与高价值事实）、case_id 与可引用证据编号；执行器
调用唯一模型客户端并按 M2-04 上下文严格校验，附加"每张发送图片必须有一条
观察"覆盖检查；模糊图不得从文本反推图片事实由合同与覆盖测试固定。
"""

from __future__ import annotations

import base64
import json

import pytest
from perception_samples import (
    CASE_ID,
    loaded_case_input,
    perception_unknown_image_json,
    perception_valid_json,
)

from app.contracts.analysis import AnalysisErrorCode, AnalysisStage
from app.modules.analysis.client import GlmClientError, GlmResponse, ScriptedGlmClient
from app.modules.analysis.perception import (
    PerceptionStageInput,
    build_perception_request,
    run_perception_stage,
)
from app.modules.analysis.prompts import load_stage_prompt

pytestmark = pytest.mark.task_m2_05

_JPEG_BYTES = b"\xff\xd8\xff\xe0fake-jpeg"


def image_resolver(mapping: dict[str, tuple[str, bytes]] | None = None):
    resolved = mapping if mapping is not None else {
        "assets/img_0001.jpg": ("image/jpeg", _JPEG_BYTES)
    }

    def resolve(asset_relative_path: str) -> tuple[str, bytes]:
        if asset_relative_path not in resolved:
            raise FileNotFoundError(asset_relative_path)
        return resolved[asset_relative_path]

    return resolve


def stage_input(**overrides) -> PerceptionStageInput:
    kwargs = {
        "case_input": loaded_case_input(),
        "image_data_resolver": image_resolver(),
    }
    kwargs.update(overrides)
    return PerceptionStageInput(**kwargs)


class TestInputBuilder:
    """感知输入最小权限：对话、图片、已核验订单事实、case_id、证据编号。"""

    def test_request_carries_perception_prompt(self) -> None:
        request = build_perception_request(
            stage_input(), prompt=load_stage_prompt(AnalysisStage.PERCEPTION)
        )

        assert request.stage is AnalysisStage.PERCEPTION
        assert request.system_prompt == load_stage_prompt(
            AnalysisStage.PERCEPTION
        ).rendered_text

    def test_user_content_contains_dialogue_with_ids_and_roles(self) -> None:
        request = build_perception_request(
            stage_input(), prompt=load_stage_prompt(AnalysisStage.PERCEPTION)
        )

        assert f"case_id: {CASE_ID}" in request.user_content
        msg_one = request.user_content.index("[msg-0001]")
        msg_two = request.user_content.index("[msg-0002]")
        assert msg_one < msg_two
        assert "我买的搅拌机用了三天就冒烟了" in request.user_content
        assert "（CUSTOMER）" in request.user_content
        assert "（SERVICE_AGENT）" in request.user_content

    def test_user_content_contains_verified_order_facts(self) -> None:
        request = build_perception_request(
            stage_input(), prompt=load_stage_prompt(AnalysisStage.PERCEPTION)
        )

        assert "[beh-0001] ORDER_STATUS: delivered" in request.user_content

    def test_payment_total_and_high_value_fact_never_enter_request(self) -> None:
        """付款金额只供追溯；高价值结论与 RFM 是感知阶段禁止读取内容。"""
        request = build_perception_request(
            stage_input(), prompt=load_stage_prompt(AnalysisStage.PERCEPTION)
        )

        assert "[beh-0002]" not in request.user_content
        assert "189.90" not in request.user_content
        assert "is_high_value" not in request.user_content
        assert "r_p75" not in request.user_content
        assert "customer_value" not in request.user_content

    def test_images_attached_with_evidence_ids(self) -> None:
        request = build_perception_request(
            stage_input(), prompt=load_stage_prompt(AnalysisStage.PERCEPTION)
        )

        assert len(request.images) == 1
        assert request.images[0].media_type == "image/jpeg"
        assert (
            request.images[0].data_base64
            == base64.b64encode(_JPEG_BYTES).decode("ascii")
        )
        assert "[img-0001]" in request.user_content

    def test_unresolvable_image_is_omitted_and_not_citable(self) -> None:
        request = build_perception_request(
            stage_input(image_data_resolver=image_resolver({})),
            prompt=load_stage_prompt(AnalysisStage.PERCEPTION),
        )

        assert request.images == ()
        assert "[img-0001]" not in request.user_content


class TestExecutor:
    """执行器：唯一客户端调用 + 严格校验 + 图片观察覆盖检查。"""

    def test_valid_output_passes_with_manifest(self) -> None:
        client = ScriptedGlmClient([GlmResponse(content=perception_valid_json())])

        result = run_perception_stage(
            stage_input(),
            model_client=client,
            case_id=CASE_ID,
        )

        assert result.model_error is None
        assert result.outcome is not None and result.outcome.ok
        assert result.attempts[0].request_manifest is not None
        assert "system_prompt_sha256" in result.attempts[0].request_manifest

    def test_unknown_image_without_facts_passes(self) -> None:
        client = ScriptedGlmClient([GlmResponse(content=perception_unknown_image_json())])

        result = run_perception_stage(
            stage_input(),
            model_client=client,
            case_id=CASE_ID,
        )

        assert result.outcome is not None and result.outcome.ok

    def test_missing_image_observation_is_flagged(self) -> None:
        """发送了的图片必须有一条观察，缺失即返回可修复覆盖错误。"""
        raw = json.loads(perception_valid_json())
        raw["image_observations"] = []
        client = ScriptedGlmClient([GlmResponse(content=json.dumps(raw, ensure_ascii=False))])

        result = run_perception_stage(
            stage_input(),
            model_client=client,
            case_id=CASE_ID,
        )

        assert result.outcome is not None and not result.outcome.ok
        codes = {error.code.value for error in result.outcome.errors}
        assert "IMAGE_COVERAGE_INCOMPLETE" in codes

    def test_unknown_image_with_invented_facts_rejected(self) -> None:
        """UNKNOWN 图片不得编造可观察事实（不得从文本反推图片内容）。"""
        raw = json.loads(perception_unknown_image_json())
        raw["image_observations"][0]["observable_facts"] = ["底座有烧焦痕迹。"]
        client = ScriptedGlmClient([GlmResponse(content=json.dumps(raw, ensure_ascii=False))])

        result = run_perception_stage(
            stage_input(),
            model_client=client,
            case_id=CASE_ID,
        )

        assert result.outcome is not None and not result.outcome.ok

    def test_cross_case_evidence_rejected(self) -> None:
        raw = json.loads(perception_valid_json())
        raw["events"][0]["evidence_ids"] = ["other:msg-0001"]
        client = ScriptedGlmClient([GlmResponse(content=json.dumps(raw, ensure_ascii=False))])

        result = run_perception_stage(
            stage_input(),
            model_client=client,
            case_id=CASE_ID,
        )

        assert result.outcome is not None and not result.outcome.ok
        codes = {error.code.value for error in result.outcome.errors}
        assert "EVIDENCE_NOT_ALLOWED" in codes

    def test_provider_error_recorded_for_engine(self) -> None:
        client = ScriptedGlmClient(
            [GlmClientError(AnalysisErrorCode.MODEL_NETWORK, "连接中断")]
        )

        result = run_perception_stage(
            stage_input(),
            model_client=client,
            case_id=CASE_ID,
        )

        assert result.outcome is None
        assert result.model_error is not None
        assert result.model_error.error_code is AnalysisErrorCode.MODEL_NETWORK
