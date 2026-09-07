"""M2-03 验收：同合同测试客户端的脚本化行为（规格第 9.3、15.1 节）。

ScriptedGlmClient 与 GlmClient 满足同一公开协议：按脚本顺序返回预设响应或
原样抛出预设错误，记录收到的全部请求，供 M2-05 至 M2-09 的确定性测试使用。
"""

from __future__ import annotations

import pytest

from app.contracts.analysis import AnalysisErrorCode, AnalysisStage
from app.modules.analysis.client import (
    GlmClientError,
    GlmRequest,
    GlmResponse,
    ScriptedGlmClient,
)

pytestmark = pytest.mark.task_m2_03


def request(no: int) -> GlmRequest:
    return GlmRequest(
        stage=AnalysisStage.PERCEPTION,
        prompt_version="v1",
        system_prompt=f"提示词 {no}",
        user_content=f"输入 {no}",
    )


class TestScriptedClientBehavior:
    def test_returns_scripted_responses_in_order(self) -> None:
        responses = [
            GlmResponse(content='{"a": 1}', prompt_tokens=10, completion_tokens=5, total_tokens=15),
            GlmResponse(content='{"a": 2}', prompt_tokens=11, completion_tokens=6, total_tokens=17),
        ]
        client = ScriptedGlmClient(responses)

        first = client.complete(request(1))
        second = client.complete(request(2))

        assert first.content == '{"a": 1}'
        assert second.content == '{"a": 2}'
        assert [r.user_content for r in client.requests] == ["输入 1", "输入 2"]

    def test_raises_scripted_error_preserving_classification(self) -> None:
        scripted_error = GlmClientError(
            error_code=AnalysisErrorCode.MODEL_RATE_LIMITED, detail="供应商限流"
        )
        client = ScriptedGlmClient(
            [
                GlmResponse(content="{}", prompt_tokens=1, completion_tokens=1, total_tokens=2),
                scripted_error,
            ]
        )

        assert client.complete(request(1)).content == "{}"
        with pytest.raises(GlmClientError) as exc_info:
            client.complete(request(2))

        assert exc_info.value is scripted_error
        assert exc_info.value.error_code == AnalysisErrorCode.MODEL_RATE_LIMITED

    def test_exhausted_script_fails_loudly(self) -> None:
        client = ScriptedGlmClient(
            [GlmResponse(content="{}", prompt_tokens=1, completion_tokens=1, total_tokens=2)]
        )
        client.complete(request(1))

        with pytest.raises(AssertionError, match="脚本"):
            client.complete(request(2))

    def test_default_construction_records_requests_without_outcomes(self) -> None:
        client = ScriptedGlmClient()

        with pytest.raises(AssertionError):
            client.complete(request(1))
        assert len(client.requests) == 1
