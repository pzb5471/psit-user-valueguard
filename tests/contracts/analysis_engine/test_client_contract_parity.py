"""M2-09 合同验收：GlmClient 与 ScriptedGlmClient 合同一致性（规格第 9.3、15.1 节）。

真实客户端（注入伪 SDK，零网络）与测试客户端必须满足同一
AnalysisModelClient 协议：同一请求产出同构响应，供应商异常映射到同一组
稳定错误码。M3 接线依据该一致性替换客户端而不改变引擎行为。
"""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
from zai.core import (
    APIAuthenticationError,
    APIInternalError,
    APIReachLimitError,
    APIRequestFailedError,
    APITimeoutError,
)

from app.contracts.analysis import AnalysisErrorCode, AnalysisStage
from app.modules.analysis.client import (
    AnalysisModelClient,
    GlmCallParams,
    GlmClient,
    GlmClientError,
    GlmRequest,
    GlmResponse,
    ScriptedGlmClient,
)

pytestmark = pytest.mark.task_m2_09

REQUEST = GlmRequest(
    stage=AnalysisStage.PERCEPTION,
    prompt_version="v1",
    system_prompt="系统提示词",
    user_content="用户输入",
)

# GlmClient 构造要求非空密钥；本测试注入伪 SDK，密钥值不参与任何真实调用。
_PLACEHOLDER_KEY = "*" * 12

_SUCCESS_COMPLETION = SimpleNamespace(
    choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))],
    usage=SimpleNamespace(prompt_tokens=11, completion_tokens=7, total_tokens=18),
)


class _FakeCompletions:
    def __init__(self, outcome: object) -> None:
        self._outcome = outcome

    def create(self, **_kwargs: object) -> object:
        outcome = self._outcome
        if isinstance(outcome, Raises):
            raise outcome.error
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class Raises:
    """哨兵：标记伪 SDK 应抛出的异常。"""

    def __init__(self, error: Exception) -> None:
        self.error = error


class FakeZaiSdk:
    """最小 zai-sdk 形状：chat.completions.create 按脚本返回或抛出。"""

    def __init__(self, outcome: object) -> None:
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=_FakeCompletions(outcome).create)
        )


def real_client(outcome: object) -> GlmClient:
    return GlmClient(
        api_key=_PLACEHOLDER_KEY,
        connect_timeout_seconds=10.0,
        response_timeout_seconds=300.0,
        sdk_client=FakeZaiSdk(outcome),
    )


class TestProtocolParity:
    """两个客户端满足同一运行时协议。"""

    def test_both_satisfy_analysis_model_client_protocol(self) -> None:
        assert isinstance(real_client(_SUCCESS_COMPLETION), AnalysisModelClient)
        assert isinstance(ScriptedGlmClient(), AnalysisModelClient)


class TestResponseParity:
    """同一成功响应在两个客户端下产出同构 GlmResponse。"""

    def test_content_and_token_fields_match(self) -> None:
        scripted = ScriptedGlmClient(
            [
                GlmResponse(
                    content='{"ok": true}',
                    prompt_tokens=11,
                    completion_tokens=7,
                    total_tokens=18,
                )
            ]
        )
        real = real_client(_SUCCESS_COMPLETION)

        from_scripted = scripted.complete(REQUEST)
        from_real = real.complete(REQUEST)

        assert from_real.content == from_scripted.content == '{"ok": true}'
        assert from_real.prompt_tokens == from_scripted.prompt_tokens == 11
        assert from_real.completion_tokens == from_scripted.completion_tokens == 7
        assert from_real.total_tokens == from_scripted.total_tokens == 18


def _status_error(cls: type, status: int, message: str) -> Exception:
    return cls(message, response=httpx.Response(status, request=httpx.Request("POST", "https://x")))


def _timeout_error() -> Exception:
    return APITimeoutError(httpx.Request("POST", "https://x"))


class TestErrorParity:
    """供应商异常映射与脚本化 GlmClientError 覆盖同一组稳定错误码。"""

    @pytest.mark.parametrize(
        ("outcome", "expected_code"),
        [
            (httpx.TimeoutException("t"), AnalysisErrorCode.MODEL_TIMEOUT),
            (httpx.ConnectError("n"), AnalysisErrorCode.MODEL_NETWORK),
            (
                _status_error(APIReachLimitError, 429, "r"),
                AnalysisErrorCode.MODEL_RATE_LIMITED,
            ),
            (
                _status_error(APIAuthenticationError, 401, "a"),
                AnalysisErrorCode.MODEL_AUTH_REJECTED,
            ),
            (
                _status_error(APIAuthenticationError, 403, "f"),
                AnalysisErrorCode.MODEL_AUTH_REJECTED,
            ),
            (
                _status_error(APIInternalError, 500, "s"),
                AnalysisErrorCode.MODEL_PROVIDER_ERROR,
            ),
            (
                _status_error(APIRequestFailedError, 400, "q"),
                AnalysisErrorCode.MODEL_REQUEST_INVALID,
            ),
            (_timeout_error(), AnalysisErrorCode.MODEL_TIMEOUT),
            (httpx.TransportError("x"), AnalysisErrorCode.MODEL_NETWORK),
        ],
    )
    def test_provider_error_maps_to_stable_code(
        self, outcome: object, expected_code: AnalysisErrorCode
    ) -> None:
        with pytest.raises(GlmClientError) as excinfo:
            real_client(outcome).complete(REQUEST)

        assert excinfo.value.error_code is expected_code

    def test_scripted_client_raises_codes_from_same_enum(self) -> None:
        for code in AnalysisErrorCode:
            client = ScriptedGlmClient([GlmClientError(code, "x")])
            with pytest.raises(GlmClientError) as excinfo:
                client.complete(REQUEST)
            assert excinfo.value.error_code is code


class TestManifestParity:
    """请求清单结构冻结（v1）：真实与脚本路径产出同键清单。"""

    def test_manifest_keys_are_frozen(self) -> None:
        from app.modules.analysis.client.manifest import build_request_manifest

        manifest = build_request_manifest(
            REQUEST,
            params=GlmCallParams(),
            connect_timeout_seconds=10.0,
            response_timeout_seconds=300.0,
        )

        assert set(manifest) == {
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

    def test_real_client_manifest_matches_builder(self) -> None:
        real = real_client(_SUCCESS_COMPLETION)
        assert real.build_manifest(REQUEST)["stage"] == "PERCEPTION"
