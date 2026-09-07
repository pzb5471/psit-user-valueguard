"""唯一真实模型边界 GlmClient（M2-03，规格第 9.3 节）。

三个阶段不允许各自调用 SDK；一切供应商调用都经过本类。SDK 自动重试关闭
（max_retries=0），重试与修复编排归 M2-08 引擎所有；本类只负责请求构造、
参数读取、超时接线、供应商错误分类与请求清单产出。
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

import httpx
from zai import ZaiClient

from app.contracts.analysis import AnalysisErrorCode
from app.modules.analysis.client.errors import (
    GlmClientError,
    classify_provider_error,
    safe_detail,
)
from app.modules.analysis.client.manifest import build_request_manifest
from app.modules.analysis.client.models import GlmCallParams, GlmRequest, GlmResponse

__all__ = ["AnalysisModelClient", "GlmClient"]


@runtime_checkable
class AnalysisModelClient(Protocol):
    """三阶段共用的模型调用协议：真实客户端与测试客户端满足同一合同。"""

    def complete(self, request: GlmRequest) -> GlmResponse: ...


class GlmClient:
    """封装官方 zai-sdk 的唯一真实模型客户端。

    超时数值在装配期注入（M3 应用工厂从 Settings.glm 读取后传入）；
    M2 代码不导入 M3 模块，模块依赖方向由合同测试固定。
    """

    def __init__(
        self,
        api_key: str,
        *,
        connect_timeout_seconds: float,
        response_timeout_seconds: float,
        params: GlmCallParams | None = None,
        sdk_client: Any | None = None,
    ) -> None:
        if not api_key or not api_key.strip():
            raise ValueError("缺少 ZAI_API_KEY：GlmClient 只能在密钥已配置时构造")
        self._params = params or GlmCallParams()
        self._connect_timeout = connect_timeout_seconds
        self._response_timeout = response_timeout_seconds
        self._sensitive_error_values = tuple({api_key, api_key.strip()})
        self._sdk = (
            sdk_client
            if sdk_client is not None
            else ZaiClient(api_key=api_key, max_retries=0)
        )

    def complete(self, request: GlmRequest) -> GlmResponse:
        try:
            completion = self._sdk.chat.completions.create(
                **self._build_call_kwargs(request)
            )
        except GlmClientError:
            raise
        except Exception as error:
            raise GlmClientError(
                error_code=classify_provider_error(error),
                detail=safe_detail(
                    error, sensitive_values=self._sensitive_error_values
                ),
            ) from error
        return self._parse_response(completion)

    def build_manifest(self, request: GlmRequest) -> dict[str, Any]:
        """本次调用的请求清单；M2-08 引擎随事件原样转发。"""

        return build_request_manifest(
            request,
            params=self._params,
            connect_timeout_seconds=self._connect_timeout,
            response_timeout_seconds=self._response_timeout,
        )

    def _build_call_kwargs(self, request: GlmRequest) -> dict[str, Any]:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": request.system_prompt}
        ]
        if request.images:
            blocks: list[dict[str, Any]] = [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{image.media_type};base64,{image.data_base64}"
                    },
                }
                for image in request.images
            ]
            blocks.append({"type": "text", "text": request.user_content})
            messages.append({"role": "user", "content": blocks})
        else:
            messages.append({"role": "user", "content": request.user_content})

        call_kwargs: dict[str, Any] = {
            "model": self._params.model_name,
            "messages": messages,
            "stream": False,
            "do_sample": self._params.do_sample,
            "max_tokens": self._params.max_tokens,
            "thinking": {
                "type": "enabled" if self._params.thinking_enabled else "disabled"
            },
            "reasoning_effort": self._params.reasoning_effort,
            "timeout": httpx.Timeout(
                connect=self._connect_timeout,
                read=self._response_timeout,
                write=self._response_timeout,
                pool=self._connect_timeout,
            ),
        }
        if self._params.json_object_mode:
            call_kwargs["response_format"] = {"type": "json_object"}
        return call_kwargs

    def _parse_response(self, completion: Any) -> GlmResponse:
        try:
            content = completion.choices[0].message.content
        except (AttributeError, IndexError) as error:
            raise GlmClientError(
                error_code=AnalysisErrorCode.MODEL_PROVIDER_ERROR,
                detail="供应商响应缺少 choices/message 结构",
            ) from error
        if not isinstance(content, str) or not content.strip():
            raise GlmClientError(
                error_code=AnalysisErrorCode.MODEL_OUTPUT_INVALID,
                detail="模型返回空内容",
            )
        usage = getattr(completion, "usage", None)
        return GlmResponse(
            content=content,
            prompt_tokens=_optional_int(usage, "prompt_tokens"),
            completion_tokens=_optional_int(usage, "completion_tokens"),
            total_tokens=_optional_int(usage, "total_tokens"),
        )


def _optional_int(usage: Any, field: str) -> int | None:
    value = getattr(usage, field, None)
    return value if isinstance(value, int) else None
