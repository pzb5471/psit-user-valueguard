"""请求清单的冻结结构（M2-03）。

request_manifest 由 GlmClient 每次调用产出并随事件原样转发（分析合同
ModelAttemptFinishedEvent 注释）：只记录参数层信息与内容指纹，
不包含密钥、提示词原文、用户内容原文或供应商响应。
"""

from __future__ import annotations

import hashlib
from typing import Any

from app.modules.analysis.client.models import GlmCallParams, GlmRequest

REQUEST_MANIFEST_VERSION = "v1"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_request_manifest(
    request: GlmRequest,
    *,
    params: GlmCallParams,
    connect_timeout_seconds: float,
    response_timeout_seconds: float,
) -> dict[str, Any]:
    """构造单次调用的请求清单；相同请求与参数产出完全相同的清单。"""

    return {
        "manifest_version": REQUEST_MANIFEST_VERSION,
        "model": params.model_name,
        "stage": request.stage.value,
        "prompt_version": request.prompt_version,
        "system_prompt_sha256": _sha256(request.system_prompt),
        "user_content_sha256": _sha256(request.user_content),
        "image_count": len(request.images),
        "stream": False,
        "json_object_mode": params.json_object_mode,
        "thinking_enabled": params.thinking_enabled,
        "reasoning_effort": params.reasoning_effort,
        "do_sample": params.do_sample,
        "max_tokens": params.max_tokens,
        "connect_timeout_seconds": connect_timeout_seconds,
        "response_timeout_seconds": response_timeout_seconds,
    }
