"""GlmClient 错误类型与供应商错误分类（M2-03，规格第 9.3 节）。

分类结果是稳定错误码：MODEL_TIMEOUT、MODEL_NETWORK、MODEL_RATE_LIMITED、
MODEL_PROVIDER_ERROR 可重试；MODEL_AUTH_REJECTED、MODEL_REQUEST_INVALID 不重试；
MODEL_OUTPUT_INVALID 表示模型已返回但内容不可用。错误消息与序列化结果
不得携带密钥（由测试固定）。
"""

from __future__ import annotations

import httpx
from zai.core import (
    APIAuthenticationError,
    APIInternalError,
    APIReachLimitError,
    APIRequestFailedError,
    APITimeoutError,
)

from app.contracts.analysis import AnalysisErrorCode

__all__ = ["GlmClientError", "classify_provider_error"]

_MAX_DETAIL_LENGTH = 512


class GlmClientError(Exception):
    """携带稳定错误分类的模型调用失败。"""

    def __init__(self, error_code: AnalysisErrorCode, detail: str) -> None:
        self.error_code = error_code
        self.detail = detail
        super().__init__(f"{error_code.value}: {detail}")

    def to_dict(self) -> dict[str, str]:
        return {"error_code": self.error_code.value, "detail": self.detail}


def _status_code_of(error: BaseException) -> int | None:
    status_code = getattr(error, "status_code", None)
    return status_code if isinstance(status_code, int) else None


def classify_provider_error(error: BaseException) -> AnalysisErrorCode:
    """把任意供应商侧异常分类为稳定错误码；未知错误按可重试供应商错误兜底。"""

    if isinstance(error, GlmClientError):
        return error.error_code

    status_code = _status_code_of(error)
    if status_code is not None:
        if status_code in (401, 403):
            return AnalysisErrorCode.MODEL_AUTH_REJECTED
        if status_code == 429:
            return AnalysisErrorCode.MODEL_RATE_LIMITED
        if status_code >= 500:
            return AnalysisErrorCode.MODEL_PROVIDER_ERROR
        return AnalysisErrorCode.MODEL_REQUEST_INVALID

    if isinstance(error, APITimeoutError):
        return AnalysisErrorCode.MODEL_TIMEOUT
    if isinstance(error, httpx.TimeoutException):
        return AnalysisErrorCode.MODEL_TIMEOUT
    if isinstance(error, httpx.TransportError):
        return AnalysisErrorCode.MODEL_NETWORK
    if isinstance(error, APIReachLimitError):
        return AnalysisErrorCode.MODEL_RATE_LIMITED
    if isinstance(error, APIAuthenticationError):
        return AnalysisErrorCode.MODEL_AUTH_REJECTED
    if isinstance(error, APIInternalError):
        return AnalysisErrorCode.MODEL_PROVIDER_ERROR
    if isinstance(error, APIRequestFailedError):
        return AnalysisErrorCode.MODEL_REQUEST_INVALID
    return AnalysisErrorCode.MODEL_PROVIDER_ERROR


def safe_detail(
    error: BaseException, *, sensitive_values: tuple[str, ...] = ()
) -> str:
    """脱敏并截断错误描述；只取异常文本，不追加任何请求上下文。"""

    detail = str(error).strip() or error.__class__.__name__
    for value in sorted(set(sensitive_values), key=len, reverse=True):
        if value:
            detail = detail.replace(value, "[REDACTED]")
    return detail[:_MAX_DETAIL_LENGTH]
