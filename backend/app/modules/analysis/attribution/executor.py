"""归因阶段执行器（M2-06，规格第 7.1、7.2、9.2、9.3 节）。

单次执行 = 构造请求 → 唯一客户端调用 → M2-04 严格校验。执行器不做重试与
修复编排（归 M2-08 引擎），但记录每次尝试的请求、响应或错误、耗时与
请求清单，供引擎产出类型化事件；请求清单只含参数层信息与内容指纹。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from app.contracts.analysis import AnalysisErrorCode, AnalysisStage
from app.modules.analysis.attribution.input_builder import (
    AttributionStageInput,
    build_attribution_request,
)
from app.modules.analysis.client import (
    AnalysisModelClient,
    GlmClientError,
    GlmRequest,
    GlmResponse,
)
from app.modules.analysis.client.manifest import build_request_manifest
from app.modules.analysis.client.models import GlmCallParams
from app.modules.analysis.prompts import StagePrompt, load_stage_prompt
from app.modules.analysis.validation import (
    AttributionValidationContext,
    StageValidationOutcome,
    perception_cited_evidence_ids,
    validate_stage_result,
)

__all__ = [
    "AttributionStageResult",
    "ModelAttemptRecord",
    "run_attribution_stage",
]

DEFAULT_CONNECT_TIMEOUT_SECONDS = 10.0
DEFAULT_RESPONSE_TIMEOUT_SECONDS = 300.0
_DEFAULT_CALL_PARAMS = GlmCallParams()


@dataclass(frozen=True)
class ModelAttemptRecord:
    """单次模型尝试：请求、响应或错误、耗时与请求清单（规格第 9.3 节）。"""

    request: GlmRequest
    response: GlmResponse | None
    error_code: AnalysisErrorCode | None
    error_summary: str | None
    latency_ms: int | None
    request_manifest: dict[str, Any]


@dataclass(frozen=True)
class AttributionStageResult:
    """归因阶段执行结果：模型错误、校验后结果与全部尝试记录。"""

    outcome: StageValidationOutcome | None
    model_error: GlmClientError | None
    attempts: tuple[ModelAttemptRecord, ...]


def run_attribution_stage(
    stage_input: AttributionStageInput,
    *,
    model_client: AnalysisModelClient,
    case_id: str,
    allowed_evidence_ids: frozenset[str],
    prompt: StagePrompt | None = None,
    params: GlmCallParams = _DEFAULT_CALL_PARAMS,
    connect_timeout_seconds: float = DEFAULT_CONNECT_TIMEOUT_SECONDS,
    response_timeout_seconds: float = DEFAULT_RESPONSE_TIMEOUT_SECONDS,
) -> AttributionStageResult:
    """执行一次归因阶段；供应商错误与校验失败都原样返回给引擎编排。"""

    stage_prompt = prompt or load_stage_prompt(AnalysisStage.ATTRIBUTION)
    request = build_attribution_request(stage_input, prompt=stage_prompt)
    manifest = build_request_manifest(
        request,
        params=params,
        connect_timeout_seconds=connect_timeout_seconds,
        response_timeout_seconds=response_timeout_seconds,
    )

    started = time.monotonic()
    try:
        response = model_client.complete(request)
    except GlmClientError as error:
        return AttributionStageResult(
            outcome=None,
            model_error=error,
            attempts=(
                ModelAttemptRecord(
                    request=request,
                    response=None,
                    error_code=error.error_code,
                    error_summary=error.detail,
                    latency_ms=_elapsed_ms(started),
                    request_manifest=manifest,
                ),
            ),
        )

    context = AttributionValidationContext(
        case_id=case_id,
        allowed_evidence_ids=allowed_evidence_ids,
        upstream_cited_ids=perception_cited_evidence_ids(stage_input.perception),
    )
    outcome = validate_stage_result(AnalysisStage.ATTRIBUTION, response.content, context)
    return AttributionStageResult(
        outcome=outcome,
        model_error=None,
        attempts=(
            ModelAttemptRecord(
                request=request,
                response=response,
                error_code=None,
                error_summary=None,
                latency_ms=_elapsed_ms(started),
                request_manifest=manifest,
            ),
        ),
    )


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)
