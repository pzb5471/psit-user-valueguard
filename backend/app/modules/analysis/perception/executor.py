"""感知阶段执行器（M2-05，规格第 7.1、9.2、9.3 节）。

单次执行 = 构造请求 → 唯一客户端调用 → M2-04 严格校验 → 图片观察覆盖检查
（每张实际发送的图片必须对应一条 ImageObservation）。重试与修复编排归
M2-08 引擎；尝试记录只含参数与内容指纹，不含提示词原文与图片数据。
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from app.contracts.analysis import AnalysisStage, PerceptionResult
from app.contracts.data import EvidenceRole
from app.modules.analysis.attribution import ModelAttemptRecord
from app.modules.analysis.client import (
    AnalysisModelClient,
    GlmClientError,
)
from app.modules.analysis.client.manifest import build_request_manifest
from app.modules.analysis.client.models import GlmCallParams
from app.modules.analysis.perception.input_builder import (
    PerceptionStageInput,
    build_perception_request,
    citable_evidence_ids,
)
from app.modules.analysis.prompts import StagePrompt, load_stage_prompt
from app.modules.analysis.validation import (
    PerceptionValidationContext,
    StageValidationError,
    StageValidationOutcome,
    ValidationErrorCode,
    validate_stage_result,
)

__all__ = [
    "PerceptionStageResult",
    "run_perception_stage",
    "validate_perception_response",
]

DEFAULT_CONNECT_TIMEOUT_SECONDS = 10.0
DEFAULT_RESPONSE_TIMEOUT_SECONDS = 300.0
_DEFAULT_CALL_PARAMS = GlmCallParams()


@dataclass(frozen=True)
class PerceptionStageResult:
    """感知阶段执行结果：模型错误、校验后结果与尝试记录。"""

    outcome: StageValidationOutcome | None
    model_error: GlmClientError | None
    attempts: tuple[ModelAttemptRecord, ...]


def run_perception_stage(
    stage_input: PerceptionStageInput,
    *,
    model_client: AnalysisModelClient,
    case_id: str,
    prompt: StagePrompt | None = None,
    params: GlmCallParams = _DEFAULT_CALL_PARAMS,
    connect_timeout_seconds: float = DEFAULT_CONNECT_TIMEOUT_SECONDS,
    response_timeout_seconds: float = DEFAULT_RESPONSE_TIMEOUT_SECONDS,
) -> PerceptionStageResult:
    """执行一次感知阶段；供应商错误与校验失败原样返回给引擎编排。"""

    stage_prompt = prompt or load_stage_prompt(AnalysisStage.PERCEPTION)
    request = build_perception_request(stage_input, prompt=stage_prompt)
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
        return PerceptionStageResult(
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

    outcome = validate_perception_response(
        response.content, stage_input=stage_input, case_id=case_id
    )
    return PerceptionStageResult(
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


def validate_perception_response(
    content: str, *, stage_input: PerceptionStageInput, case_id: str
) -> StageValidationOutcome:
    """对初次与修复响应执行同一组感知校验。"""

    allowed_evidence_ids = citable_evidence_ids(stage_input)
    text_evidence_ids = frozenset(
        item.evidence_id for item in stage_input.case_input.evidence.text_items
    )
    customer_text_evidence_ids = frozenset(
        item.evidence_id
        for item in stage_input.case_input.evidence.text_items
        if item.role is EvidenceRole.CUSTOMER
    )
    image_ids = frozenset(
        image.evidence_id for image in stage_input.case_input.evidence.image_items
    )
    attached_image_evidence_ids = allowed_evidence_ids & image_ids
    context = PerceptionValidationContext(
        case_id=case_id,
        allowed_evidence_ids=allowed_evidence_ids,
        customer_text_evidence_ids=customer_text_evidence_ids,
        text_evidence_ids=text_evidence_ids,
        image_evidence_ids=attached_image_evidence_ids,
    )
    outcome = validate_stage_result(AnalysisStage.PERCEPTION, content, context)
    return _check_image_coverage(outcome, attached_image_evidence_ids)


def _check_image_coverage(
    outcome: StageValidationOutcome, attached_image_evidence_ids: frozenset[str]
) -> StageValidationOutcome:
    """发送了的每张图片必须对应一条观察（规格第 7.1 节）；缺失可定向修复。"""

    if not outcome.ok or outcome.result is None:
        return outcome
    result = outcome.result
    if not isinstance(result, PerceptionResult):
        raise RuntimeError("感知校验成功时必须返回 PerceptionResult")
    observed = {observation.image_evidence_id for observation in result.image_observations}
    missing = sorted(attached_image_evidence_ids - observed)
    if not missing:
        return outcome
    coverage_error = StageValidationError(
        code=ValidationErrorCode.IMAGE_COVERAGE_INCOMPLETE,
        stage=AnalysisStage.PERCEPTION,
        field_path="image_observations",
        message=f"发送的图片缺少观察：{'、'.join(missing)}",
        repairable=True,
    )
    return StageValidationOutcome(
        stage=outcome.stage,
        result=None,
        errors=(*outcome.errors, coverage_error),
    )


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)
