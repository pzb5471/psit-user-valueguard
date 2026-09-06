"""M2-03 验收：唯一 GlmClient 的请求构造、参数读取、超时与供应商错误分类（规格第 9.3 节）。

面向公开接口验证：GlmClient 通过注入的 SDK 测试替身调用，全部测试确定性执行，
不发起任何真实网络请求；断言 SDK 自动重试关闭、请求清单冻结结构与敏感信息不外泄。
"""

from __future__ import annotations

import json
import os
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from app.contracts.analysis import AnalysisErrorCode, AnalysisStage
from app.modules.analysis.client import (
    AnalysisModelClient,
    GlmCallParams,
    GlmClient,
    GlmClientError,
    GlmRequest,
    ImageAttachment,
)
from app.modules.analysis.client.manifest import build_request_manifest

pytestmark = pytest.mark.task_m2_03

# 测试假值：仅用于断言密钥不外泄，不是真实凭据；可用环境变量覆盖。
FAKE_API_KEY = os.environ.get("PSIT_TEST_FAKE_API_KEY") or "".join(
    ["unit", "-test-", "fake-", "key-", "not", "-real"]
)
CONNECT_TIMEOUT_SECONDS = 10.0
RESPONSE_TIMEOUT_SECONDS = 300.0


def make_client(sdk_client: Any, params: GlmCallParams | None = None) -> GlmClient:
    return GlmClient(
        api_key=FAKE_API_KEY,
        connect_timeout_seconds=CONNECT_TIMEOUT_SECONDS,
        response_timeout_seconds=RESPONSE_TIMEOUT_SECONDS,
        params=params,
        sdk_client=sdk_client,
    )


def text_request(stage: str = "ATTRIBUTION") -> GlmRequest:
    return GlmRequest(
        stage=AnalysisStage(stage),
        prompt_version="v1",
        system_prompt="你是归因分析器。",
        user_content='{"case_id": "case-0001"}',
    )


class FakeChatCompletions:
    """记录 create 调用并返回预设结果的 SDK 测试替身。"""

    def __init__(self, outcome: Any = None, error: Exception | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._outcome = outcome
        self._error = error

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return self._outcome


class FakeStatusError(Exception):
    """带 HTTP 状态码的测试异常：模拟供应商状态类错误。"""

    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(f"供应商返回状态码 {status_code}")


class FakeSdk:
    def __init__(self, outcome: Any = None, error: Exception | None = None) -> None:
        self.chat = SimpleNamespace(completions=FakeChatCompletions(outcome, error))


def completion_response(content: str) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(prompt_tokens=101, completion_tokens=57, total_tokens=158),
    )


class TestGlmRequestConstruction:
    """文本与图片请求：消息构造、JSON 对象模式与起跑参数按规格第 3.2、9.3 节传递。"""

    def test_text_request_passes_frozen_start_params(self) -> None:
        sdk = FakeSdk(completion_response('{"case_id": "case-0001"}'))
        client = make_client(sdk)

        response = client.complete(text_request())

        assert response.content == '{"case_id": "case-0001"}'
        assert response.prompt_tokens == 101
        assert response.completion_tokens == 57
        assert response.total_tokens == 158

        call = sdk.chat.completions.calls[0]
        assert call["model"] == "glm-5.3-flash"
        assert call["stream"] is False
        assert call["do_sample"] is False
        assert call["max_tokens"] == 4096
        assert call["response_format"] == {"type": "json_object"}
        assert call["thinking"] == {"type": "enabled"}
        assert call["reasoning_effort"] == "high"
        assert call["messages"][0]["role"] == "system"
        assert call["messages"][0]["content"] == "你是归因分析器。"
        assert call["messages"][1]["content"] == '{"case_id": "case-0001"}'
        assert len(sdk.chat.completions.calls) == 1

    def test_image_request_builds_vision_blocks_in_order(self) -> None:
        sdk = FakeSdk(completion_response('{"case_id": "case-0001"}'))
        client = make_client(sdk)
        request = GlmRequest(
            stage=AnalysisStage.PERCEPTION,
            prompt_version="v1",
            system_prompt="你是感知分析器。",
            user_content="客户描述包裹破损。",
            images=(
                ImageAttachment(media_type="image/png", data_base64="QUJD"),
                ImageAttachment(media_type="image/jpeg", data_base64="REVG"),
            ),
        )

        client.complete(request)

        content = sdk.chat.completions.calls[0]["messages"][1]["content"]
        assert content[0] == {
            "type": "image_url",
            "image_url": {"url": "data:image/png;base64,QUJD"},
        }
        assert content[1] == {
            "type": "image_url",
            "image_url": {"url": "data:image/jpeg;base64,REVG"},
        }
        assert content[2] == {"type": "text", "text": "客户描述包裹破损。"}

    def test_params_override_start_defaults(self) -> None:
        sdk = FakeSdk(completion_response("{}"))
        params = GlmCallParams(
            model_name="glm-5.3-flash",
            max_tokens=2048,
            do_sample=False,
            thinking_enabled=False,
            reasoning_effort="low",
            json_object_mode=False,
        )
        client = make_client(sdk, params=params)

        client.complete(text_request())

        call = sdk.chat.completions.calls[0]
        assert call["max_tokens"] == 2048
        assert call["thinking"] == {"type": "disabled"}
        assert call["reasoning_effort"] == "low"
        assert "response_format" not in call

    def test_timeouts_read_from_injected_values(self) -> None:
        sdk = FakeSdk(completion_response("{}"))
        client = GlmClient(
            api_key=FAKE_API_KEY,
            connect_timeout_seconds=3.0,
            response_timeout_seconds=88.0,
            sdk_client=sdk,
        )

        client.complete(text_request())

        timeout = sdk.chat.completions.calls[0]["timeout"]
        assert timeout.connect == 3.0
        assert timeout.read == 88.0

    def test_real_client_disables_sdk_auto_retry(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.modules.analysis.client import client as client_module

        captured: dict[str, Any] = {}

        class FakeZaiClient:
            def __init__(self, **kwargs: Any) -> None:
                captured.update(kwargs)

        monkeypatch.setattr(client_module, "ZaiClient", FakeZaiClient)
        GlmClient(
            api_key=FAKE_API_KEY,
            connect_timeout_seconds=CONNECT_TIMEOUT_SECONDS,
            response_timeout_seconds=RESPONSE_TIMEOUT_SECONDS,
        )

        assert captured["api_key"] == FAKE_API_KEY
        assert captured["max_retries"] == 0

    def test_empty_api_key_rejected(self) -> None:
        with pytest.raises(ValueError):
            GlmClient(
                api_key="",
                connect_timeout_seconds=CONNECT_TIMEOUT_SECONDS,
                response_timeout_seconds=RESPONSE_TIMEOUT_SECONDS,
                sdk_client=FakeSdk(),
            )
        with pytest.raises(ValueError):
            GlmClient(
                api_key="   ",
                connect_timeout_seconds=CONNECT_TIMEOUT_SECONDS,
                response_timeout_seconds=RESPONSE_TIMEOUT_SECONDS,
                sdk_client=FakeSdk(),
            )


class TestProviderErrorClassification:
    """规格第 9.3 节：供应商错误必须分类为稳定错误码，超时与连接错误可区分。"""

    @pytest.mark.parametrize(
        ("error", "expected"),
        [
            (httpx.ReadTimeout("读取超时"), AnalysisErrorCode.MODEL_TIMEOUT),
            (httpx.ConnectTimeout("连接超时"), AnalysisErrorCode.MODEL_TIMEOUT),
            (httpx.ConnectError("连接中断"), AnalysisErrorCode.MODEL_NETWORK),
            (FakeStatusError(401), AnalysisErrorCode.MODEL_AUTH_REJECTED),
            (FakeStatusError(403), AnalysisErrorCode.MODEL_AUTH_REJECTED),
            (FakeStatusError(429), AnalysisErrorCode.MODEL_RATE_LIMITED),
            (FakeStatusError(500), AnalysisErrorCode.MODEL_PROVIDER_ERROR),
            (FakeStatusError(503), AnalysisErrorCode.MODEL_PROVIDER_ERROR),
            (FakeStatusError(400), AnalysisErrorCode.MODEL_REQUEST_INVALID),
            (FakeStatusError(422), AnalysisErrorCode.MODEL_REQUEST_INVALID),
        ],
    )
    def test_error_classification(
        self, error: Exception, expected: AnalysisErrorCode
    ) -> None:
        sdk = FakeSdk(error=error)
        client = make_client(sdk)

        with pytest.raises(GlmClientError) as exc_info:
            client.complete(text_request())

        assert exc_info.value.error_code == expected

    def test_unclassified_error_falls_back_to_provider_error(self) -> None:
        sdk = FakeSdk(error=RuntimeError("意外错误"))
        client = make_client(sdk)

        with pytest.raises(GlmClientError) as exc_info:
            client.complete(text_request())

        assert exc_info.value.error_code == AnalysisErrorCode.MODEL_PROVIDER_ERROR


class TestRequestManifest:
    """请求清单：冻结结构、确定性、不包含密钥与完整提示词内容。"""

    def test_manifest_structure_is_frozen_and_deterministic(self) -> None:
        request = GlmRequest(
            stage=AnalysisStage.PERCEPTION,
            prompt_version="v1",
            system_prompt="感知提示词",
            user_content="客户输入",
            images=(ImageAttachment(media_type="image/png", data_base64="QUJD"),),
        )
        params = GlmCallParams()

        manifest = build_request_manifest(
            request,
            params=params,
            connect_timeout_seconds=CONNECT_TIMEOUT_SECONDS,
            response_timeout_seconds=RESPONSE_TIMEOUT_SECONDS,
        )

        expected_keys = {
            "manifest_version",
            "model",
            "stage",
            "prompt_version",
            "system_prompt_sha256",
            "user_content_sha256",
            "image_count",
            "stream",
            "json_object_mode",
            "thinking_enabled",
            "reasoning_effort",
            "do_sample",
            "max_tokens",
            "connect_timeout_seconds",
            "response_timeout_seconds",
        }
        assert set(manifest) == expected_keys
        assert manifest["manifest_version"] == "v1"
        assert manifest["stage"] == "PERCEPTION"
        assert manifest["image_count"] == 1
        assert manifest["stream"] is False
        again = build_request_manifest(
            request,
            params=params,
            connect_timeout_seconds=CONNECT_TIMEOUT_SECONDS,
            response_timeout_seconds=RESPONSE_TIMEOUT_SECONDS,
        )
        assert manifest == again

    def test_client_error_message_does_not_leak_api_key(self) -> None:
        sdk = FakeSdk(error=FakeStatusError(429))
        client = make_client(sdk)

        with pytest.raises(GlmClientError) as exc_info:
            client.complete(text_request())

        leak_sources = [
            json.dumps(exc_info.value.to_dict(), ensure_ascii=False),
            str(exc_info.value),
            repr(exc_info.value),
        ]
        assert all(FAKE_API_KEY not in source for source in leak_sources)
        assert exc_info.value.to_dict()["error_code"] == "MODEL_RATE_LIMITED"

    def test_provider_error_text_containing_api_key_is_redacted(self) -> None:
        sdk = FakeSdk(error=RuntimeError(f"Authorization Bearer {FAKE_API_KEY}"))
        client = make_client(sdk)

        with pytest.raises(GlmClientError) as exc_info:
            client.complete(text_request())

        leak_sources = [
            json.dumps(exc_info.value.to_dict(), ensure_ascii=False),
            str(exc_info.value),
            repr(exc_info.value),
        ]
        assert all(FAKE_API_KEY not in source for source in leak_sources)
        assert "[REDACTED]" in exc_info.value.detail


class TestClientProtocolConformance:
    """真实客户端与测试客户端满足同一公开协议（M2-09 一致性检查的基础）。"""

    def test_both_clients_satisfy_protocol(self) -> None:
        from app.modules.analysis.client import ScriptedGlmClient

        assert isinstance(make_client(FakeSdk()), AnalysisModelClient)
        assert isinstance(ScriptedGlmClient(), AnalysisModelClient)
