"""策略阶段执行器（M2-07，规格第 7.3、7.4、9.2、9.3 节）。

单次执行 = 构造请求 → 唯一客户端调用 → 程序底线调整（Agent 提出等级、
程序执行最低介入规则）→ M2-04 严格校验。底线调整不产生新的模型请求；
供应商错误与其余校验失败原样返回给 M2-08 引擎编排重试与定向修复。
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from pydantic import ValidationError

from app.contracts.analysis import (
    AnalysisStage,
    DecisionPackage,
    InterventionLevel,
)
from app.modules.analysis.attribution import ModelAttemptRecord
from app.modules.analysis.client import (
    AnalysisModelClient,
    GlmClientError,
)
from app.modules.analysis.client.manifest import build_request_manifest
from app.modules.analysis.client.models import GlmCallParams
from app.modules.analysis.prompts import StagePrompt, load_stage_prompt
from app.modules.analysis.strategy.floor import derive_intervention_floor
from app.modules.analysis.strategy.input_builder import (
    StrategyStageInput,
    build_strategy_request,
    upstream_cited_ids,
)
from app.modules.analysis.validation import (
    StageValidationOutcome,
    StrategyValidationContext,
    validate_stage_result,
)

__all__ = [
    "StrategyStageResult",
    "run_strategy_stage",
    "validate_strategy_response",
]

DEFAULT_CONNECT_TIMEOUT_SECONDS = 10.0
DEFAULT_RESPONSE_TIMEOUT_SECONDS = 300.0
_DEFAULT_CALL_PARAMS = GlmCallParams()

_FLOOR_NOTE = (
    "程序底线：因存在未解决严重问题或证据冲突/不足，介入等级调整为建议介入，"
    "需人工核验。"
)
_NOTE_MAX_LENGTH = 512


@dataclass(frozen=True)
class StrategyStageResult:
    """策略阶段执行结果：模型错误、校验后结果、尝试记录与底线调整标记。"""

    outcome: StageValidationOutcome | None
    model_error: GlmClientError | None
    attempts: tuple[ModelAttemptRecord, ...]
    floor_adjusted: bool


def run_strategy_stage(
    stage_input: StrategyStageInput,
    *,
    model_client: AnalysisModelClient,
    case_id: str,
    allowed_evidence_ids: frozenset[str],
    prompt: StagePrompt | None = None,
    params: GlmCallParams = _DEFAULT_CALL_PARAMS,
    connect_timeout_seconds: float = DEFAULT_CONNECT_TIMEOUT_SECONDS,
    response_timeout_seconds: float = DEFAULT_RESPONSE_TIMEOUT_SECONDS,
) -> StrategyStageResult:
    """执行一次策略阶段；底线调整与校验失败都记录在结果中交给引擎。"""

    stage_prompt = prompt or load_stage_prompt(AnalysisStage.STRATEGY)
    request = build_strategy_request(stage_input, prompt=stage_prompt)
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
        return StrategyStageResult(
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
            floor_adjusted=False,
        )

    outcome, floor_adjusted = validate_strategy_response(
        response.content,
        stage_input=stage_input,
        case_id=case_id,
        allowed_evidence_ids=allowed_evidence_ids,
    )
    return StrategyStageResult(
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
        floor_adjusted=floor_adjusted,
    )


def validate_strategy_response(
    content: str,
    *,
    stage_input: StrategyStageInput,
    case_id: str,
    allowed_evidence_ids: frozenset[str],
) -> tuple[StageValidationOutcome, bool]:
    """对初次与修复响应执行相同的程序底线与策略校验。"""

    severe_unresolved_present, evidence_conflict_or_insufficient = (
        derive_intervention_floor(stage_input.perception, stage_input.attribution)
    )
    content, floor_adjusted = _apply_program_floor(
        content, severe_unresolved_present, evidence_conflict_or_insufficient
    )
    context = StrategyValidationContext(
        case_id=case_id,
        allowed_evidence_ids=allowed_evidence_ids,
        upstream_cited_ids=frozenset(
            upstream_cited_ids(stage_input.perception, stage_input.attribution)
        ),
        catalog_action_types=frozenset(
            entry.action_type for entry in stage_input.action_catalog.actions
        ),
        severe_unresolved_present=severe_unresolved_present,
        evidence_conflict_or_insufficient=evidence_conflict_or_insufficient,
    )
    outcome = validate_stage_result(AnalysisStage.STRATEGY, content, context)
    return outcome, floor_adjusted


def _apply_program_floor(
    content: str, severe_unresolved_present: bool, evidence_conflict_or_insufficient: bool
) -> tuple[str, bool]:
    """Agent 提出等级，程序执行最低介入规则（规格第 7.4 节）。

    仅当模型输出可以解析为 DecisionPackage 且提出 NO_IMMEDIATE_INTERVENTION
    而底线不允许时，程序把等级调整为 SHOULD_INTERVENE 并补充人工核验说明；
    调整不产生新的模型请求。无法解析的内容原样交给严格校验处理。
    """

    try:
        parsed = DecisionPackage.model_validate_json(content)
    except ValidationError:
        return content, False
    if parsed.intervention_level is not InterventionLevel.NO_IMMEDIATE_INTERVENTION:
        return content, False
    if not (severe_unresolved_present or evidence_conflict_or_insufficient):
        return content, False

    note = _FLOOR_NOTE
    if parsed.caution_note:
        note = f"{note} {parsed.caution_note}"
    adjusted = parsed.model_copy(
        update={
            "intervention_level": InterventionLevel.SHOULD_INTERVENE,
            "caution_note": note[:_NOTE_MAX_LENGTH],
        }
    )
    return adjusted.model_dump_json(), True


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)
