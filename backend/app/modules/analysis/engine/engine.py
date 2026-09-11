"""M2-08 AnalysisEngine：三阶段顺序唯一阻塞入口（规格第 9、10.6 节）。

把感知、归因、策略三个阶段顺序编排为 analyze_case 唯一阻塞入口；执行有界
重试（可重试供应商错误最多两次）、一次带具体错误的定向修复、失败后立即
停止后续阶段，并输出五类类型化事件；事件持久化失败立即停止当前案例。
不创建线程池、不读写数据库、不启动服务、同一案例三阶段不并行、
每阶段供应商请求总数最多四次。
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from app.contracts.analysis import (
    AnalysisCompletedEvent,
    AnalysisErrorCode,
    AnalysisEvent,
    AnalysisEventSink,
    AnalysisFailure,
    AnalysisOutcome,
    AnalysisRequest,
    AnalysisStage,
    AnalysisSuccess,
    AttributionResult,
    DecisionPackage,
    ModelAttemptFinishedEvent,
    PerceptionResult,
    StageFailedEvent,
    StageResultValidatedEvent,
    StageStartedEvent,
)
from app.contracts.data import BehaviorFactType, CaseInput
from app.modules.analysis.attribution import (
    AttributionStageInput,
    run_attribution_stage,
)
from app.modules.analysis.client import (
    AnalysisModelClient,
    GlmCallParams,
    GlmClientError,
    GlmRequest,
)
from app.modules.analysis.client.manifest import build_request_manifest
from app.modules.analysis.perception import (
    PerceptionStageInput,
    run_perception_stage,
    validate_perception_response,
)
from app.modules.analysis.prompts import StagePrompt, load_stage_prompt
from app.modules.analysis.strategy import (
    ActionCatalogView,
    HighValueConclusion,
    StrategyStageInput,
    run_strategy_stage,
    validate_strategy_response,
)
from app.modules.analysis.validation import (
    AttributionValidationContext,
    StageValidationError,
    StageValidationOutcome,
    perception_cited_evidence_ids,
    validate_stage_result,
)

__all__ = ["AnalysisEngine"]

_RETRYABLE_CODES = frozenset(
    {
        AnalysisErrorCode.MODEL_TIMEOUT,
        AnalysisErrorCode.MODEL_NETWORK,
        AnalysisErrorCode.MODEL_RATE_LIMITED,
        AnalysisErrorCode.MODEL_PROVIDER_ERROR,
    }
)
_MAX_NETWORK_RETRIES = 2
_MAX_REQUESTS_PER_STAGE = 4
_RESULT_CONTRACT_VERSION = "v1"
_REPAIR_NOTE_HEADER = "上次输出未通过严格校验，错误如下："
_REPAIR_NOTE_TAIL = "请只输出修正后的 JSON 对象，不要输出任何其他内容。"

_ImageResolver = Callable[[str], tuple[str, bytes]]
_CaseImageResolver = Callable[[CaseInput, str], tuple[str, bytes]]
_ShutdownRequested = Callable[[], bool]


class AnalysisEngine:
    """M2 唯一公开编排入口：三阶段顺序、有界重试、一次修复、类型化事件。"""

    def __init__(
        self,
        *,
        model_client: AnalysisModelClient,
        image_data_resolver: _ImageResolver,
        case_image_data_resolver: _CaseImageResolver | None = None,
        action_catalog: ActionCatalogView,
        prompts: dict[AnalysisStage, StagePrompt] | None = None,
        params: GlmCallParams | None = None,
        connect_timeout_seconds: float = 10.0,
        response_timeout_seconds: float = 300.0,
        shutdown_requested: _ShutdownRequested | None = None,
    ) -> None:
        self._model_client = model_client
        self._image_data_resolver = image_data_resolver
        self._case_image_data_resolver = case_image_data_resolver
        self._action_catalog = action_catalog
        self._prompts: dict[AnalysisStage, StagePrompt] = prompts or {
            stage: load_stage_prompt(stage) for stage in AnalysisStage
        }
        self._params = params or GlmCallParams()
        self._connect_timeout = connect_timeout_seconds
        self._response_timeout = response_timeout_seconds
        self._shutdown_requested = shutdown_requested or (lambda: False)
        self._closed = False

    def close(self) -> None:
        """关闭引擎：幂等；关闭后不再接受新的 analyze_case 调用。"""

        self._closed = True

    def analyze_case(
        self, request: AnalysisRequest, event_sink: AnalysisEventSink
    ) -> AnalysisOutcome:
        """同步阻塞执行一个案例的三阶段分析；失败后立即停止后续阶段。"""

        if self._is_shutdown_requested():
            raise RuntimeError("AnalysisEngine 已关闭，不能继续 analyze_case")

        version_failure = self._check_request_versions(request)
        if version_failure is not None:
            return self._emit_completed_failure(request, event_sink, version_failure)

        if not isinstance(request.case_input, CaseInput):
            return self._emit_completed_failure(
                request,
                event_sink,
                _failure(
                    request.trace_id,
                    AnalysisErrorCode.INPUT_CONTRACT_INVALID,
                    AnalysisStage.PERCEPTION,
                    attempts_exhausted=False,
                ),
            )

        runner = _StageRunner(engine=self, request=request, event_sink=event_sink)
        return runner.run(request.case_input)

    def _is_shutdown_requested(self) -> bool:
        return self._closed or self._shutdown_requested()

    # ---- 请求级检查 ----

    def _check_request_versions(
        self, request: AnalysisRequest
    ) -> AnalysisFailure | None:
        expected = {
            AnalysisStage.PERCEPTION: request.perception_prompt_version,
            AnalysisStage.ATTRIBUTION: request.attribution_prompt_version,
            AnalysisStage.STRATEGY: request.strategy_prompt_version,
        }
        for stage, version in expected.items():
            if self._prompts[stage].version != version:
                return _failure(
                    request.trace_id,
                    AnalysisErrorCode.INPUT_CONTRACT_INVALID,
                    stage,
                    attempts_exhausted=False,
                )
        contract_versions = {
            AnalysisStage.PERCEPTION: request.perception_contract_version,
            AnalysisStage.ATTRIBUTION: request.attribution_contract_version,
            AnalysisStage.STRATEGY: request.strategy_contract_version,
        }
        for stage, version in contract_versions.items():
            if version != _RESULT_CONTRACT_VERSION:
                return _failure(
                    request.trace_id,
                    AnalysisErrorCode.INPUT_CONTRACT_INVALID,
                    stage,
                    attempts_exhausted=False,
                )
        if self._action_catalog.catalog_version != request.action_catalog_version:
            return _failure(
                request.trace_id,
                AnalysisErrorCode.INPUT_CONTRACT_INVALID,
                AnalysisStage.STRATEGY,
                attempts_exhausted=False,
            )
        return None

    def _emit_completed_failure(
        self,
        request: AnalysisRequest,
        event_sink: AnalysisEventSink,
        failure: AnalysisFailure,
    ) -> AnalysisOutcome:
        try:
            event_sink.emit(
                AnalysisCompletedEvent(
                    event_type="ANALYSIS_COMPLETED",
                    status="FAILED",
                    finished_at=_now(),
                    error_stage=failure.error_stage,
                    error_code=failure.error_code,
                )
            )
        except Exception:
            return _failure(
                request.trace_id,
                AnalysisErrorCode.EVENT_SINK_FAILED,
                failure.error_stage,
                attempts_exhausted=False,
            )
        return failure


class _StageRunner:
    """单次 analyze_case 的阶段编排状态机（不跨案例复用）。"""

    def __init__(
        self,
        *,
        engine: AnalysisEngine,
        request: AnalysisRequest,
        event_sink: AnalysisEventSink,
    ) -> None:
        self._engine = engine
        self._request = request
        self._sink = event_sink

    def run(self, case: CaseInput) -> AnalysisOutcome:
        perception = self._run_perception(case)
        if isinstance(perception, AnalysisFailure):
            return perception
        attribution = self._run_attribution(case, perception)
        if isinstance(attribution, AnalysisFailure):
            return attribution
        decision = self._run_strategy(case, perception, attribution)
        if isinstance(decision, AnalysisFailure):
            return decision

        if not self._emit(
            AnalysisCompletedEvent(
                event_type="ANALYSIS_COMPLETED",
                status="SUCCESS",
                finished_at=_now(),
            )
        ):
            return self._sink_failure(AnalysisStage.STRATEGY)
        return AnalysisSuccess(
            status="SUCCESS",
            perception=perception,
            attribution=attribution,
            decision=decision,
        )

    # ---- 感知 ----

    def _run_perception(self, case: CaseInput) -> PerceptionResult | AnalysisFailure:
        stage = AnalysisStage.PERCEPTION
        if self._engine._is_shutdown_requested():
            return self._interrupt_before(stage)
        if not self._emit(
            StageStartedEvent(event_type="STAGE_STARTED", stage=stage, started_at=_now())
        ):
            return self._sink_failure(stage)

        image_resolver = self._engine._image_data_resolver
        case_image_resolver = self._engine._case_image_data_resolver
        if case_image_resolver is not None:
            def resolve_current_case(path: str) -> tuple[str, bytes]:
                return case_image_resolver(case, path)

            image_resolver = resolve_current_case
        stage_input = PerceptionStageInput(
            case_input=case,
            image_data_resolver=image_resolver,
        )

        def executor() -> Any:
            return run_perception_stage(
                stage_input,
                model_client=self._engine._model_client,
                case_id=case.case_id,
                prompt=self._engine._prompts[stage],
                params=self._engine._params,
                connect_timeout_seconds=self._engine._connect_timeout,
                response_timeout_seconds=self._engine._response_timeout,
            )

        def validate_response(content: str) -> StageValidationOutcome:
            return validate_perception_response(
                content,
                stage_input=stage_input,
                case_id=case.case_id,
            )

        return self._drive_stage(
            stage=stage,
            executor=executor,
            validate_response=validate_response,
            contract_version=self._request.perception_contract_version,
        )

    # ---- 归因 ----

    def _run_attribution(
        self, case: CaseInput, perception: PerceptionResult
    ) -> AttributionResult | AnalysisFailure:
        stage = AnalysisStage.ATTRIBUTION
        if self._engine._is_shutdown_requested():
            return self._interrupt_before(stage)
        if not self._emit(
            StageStartedEvent(event_type="STAGE_STARTED", stage=stage, started_at=_now())
        ):
            return self._sink_failure(stage)

        def executor() -> Any:
            return run_attribution_stage(
                AttributionStageInput(
                    perception=perception,
                    evidence_content=_evidence_content(case),
                ),
                model_client=self._engine._model_client,
                case_id=case.case_id,
                allowed_evidence_ids=_case_allowed_ids(case),
                prompt=self._engine._prompts[stage],
                params=self._engine._params,
                connect_timeout_seconds=self._engine._connect_timeout,
                response_timeout_seconds=self._engine._response_timeout,
            )

        context = AttributionValidationContext(
            case_id=case.case_id,
            allowed_evidence_ids=_case_allowed_ids(case),
            upstream_cited_ids=perception_cited_evidence_ids(perception),
        )

        def validate_response(content: str) -> StageValidationOutcome:
            return validate_stage_result(stage, content, context)

        return self._drive_stage(
            stage=stage,
            executor=executor,
            validate_response=validate_response,
            contract_version=self._request.attribution_contract_version,
        )

    # ---- 策略 ----

    def _run_strategy(
        self,
        case: CaseInput,
        perception: PerceptionResult,
        attribution: AttributionResult,
    ) -> DecisionPackage | AnalysisFailure:
        stage = AnalysisStage.STRATEGY
        if self._engine._is_shutdown_requested():
            return self._interrupt_before(stage)
        if not self._emit(
            StageStartedEvent(event_type="STAGE_STARTED", stage=stage, started_at=_now())
        ):
            return self._sink_failure(stage)

        stage_input = StrategyStageInput(
            perception=perception,
            attribution=attribution,
            high_value_conclusion=HighValueConclusion(
                is_high_value=case.customer_value.is_high_value,
                decision_reason=case.customer_value.decision_reason,
            ),
            action_catalog=self._engine._action_catalog,
            evidence_content=_evidence_content(case),
        )

        def executor() -> Any:
            return run_strategy_stage(
                stage_input,
                model_client=self._engine._model_client,
                case_id=case.case_id,
                allowed_evidence_ids=_case_allowed_ids(case),
                prompt=self._engine._prompts[stage],
                params=self._engine._params,
                connect_timeout_seconds=self._engine._connect_timeout,
                response_timeout_seconds=self._engine._response_timeout,
            )

        def validate_response(content: str) -> StageValidationOutcome:
            outcome, _ = validate_strategy_response(
                content,
                stage_input=stage_input,
                case_id=case.case_id,
                allowed_evidence_ids=_case_allowed_ids(case),
            )
            return outcome

        return self._drive_stage(
            stage=stage,
            executor=executor,
            validate_response=validate_response,
            contract_version=self._request.strategy_contract_version,
        )

    # ---- 阶段驱动：有界重试、一次修复、类型化事件 ----

    def _drive_stage(
        self,
        *,
        stage: AnalysisStage,
        executor: Callable[[], Any],
        validate_response: Callable[[str], StageValidationOutcome],
        contract_version: str,
    ) -> Any:
        attempts = 0
        network_retries = 0
        last_request: GlmRequest | None = None

        while True:
            started_at = _now()
            stage_result = executor()
            finished_at = _now()
            attempts += 1

            for offset, attempt in enumerate(stage_result.attempts):
                last_request = attempt.request
                if self._emit(
                    _attempt_event(
                        stage=stage,
                        attempt_no=attempts + offset,
                        attempt=attempt,
                        prompt_version=self._engine._prompts[stage].version,
                        engine=self._engine,
                        started_at=started_at,
                        finished_at=finished_at,
                    )
                ):
                    continue
                return self._sink_failure(stage)

            if stage_result.model_error is not None:
                code = stage_result.model_error.error_code
                if code in _RETRYABLE_CODES and network_retries < _MAX_NETWORK_RETRIES:
                    network_retries += 1
                    continue
                return self._fail_stage(
                    stage,
                    code,
                    attempts_exhausted=code in _RETRYABLE_CODES,
                    error_detail=stage_result.model_error.detail,
                )

            outcome: StageValidationOutcome | None = stage_result.outcome
            if outcome is None:
                raise RuntimeError("阶段执行器未返回模型错误或校验结果")
            if outcome.ok:
                return self._accept_stage_result(stage, contract_version, outcome)

            # 结构不合格：只允许一次带具体错误的定向修复（规格第 9.3 节）。
            if any(not error.repairable for error in outcome.errors):
                return self._fail_stage(
                    stage,
                    AnalysisErrorCode.MODEL_OUTPUT_INVALID,
                    attempts_exhausted=False,
                    error_detail=outcome.errors[0].message,
                )
            if attempts >= _MAX_REQUESTS_PER_STAGE:
                return self._fail_stage(
                    stage,
                    AnalysisErrorCode.MODEL_OUTPUT_INVALID,
                    attempts_exhausted=True,
                    error_detail=outcome.errors[0].message if outcome.errors else None,
                )
            repair_request = _build_repair_request(last_request, outcome.errors)
            return self._run_repair(
                stage=stage,
                attempt_no=attempts + 1,
                repair_request=repair_request,
                validate_response=validate_response,
                contract_version=contract_version,
            )

    # ---- 事件与失败辅助 ----

    def _run_repair(
        self,
        *,
        stage: AnalysisStage,
        attempt_no: int,
        repair_request: GlmRequest,
        validate_response: Callable[[str], StageValidationOutcome],
        contract_version: str,
    ) -> Any:
        """执行唯一一次定向修复，并完整记录该次供应商调用。"""

        started_at = _now()
        try:
            response = self._engine._model_client.complete(repair_request)
        except GlmClientError as error:
            finished_at = _now()
            if not self._emit(
                _failed_attempt_event(
                    stage=stage,
                    attempt_no=attempt_no,
                    request=repair_request,
                    error=error,
                    prompt_version=self._engine._prompts[stage].version,
                    engine=self._engine,
                    started_at=started_at,
                    finished_at=finished_at,
                )
            ):
                return self._sink_failure(stage)
            return self._fail_stage(
                stage,
                error.error_code,
                attempts_exhausted=True,
                error_detail=error.detail,
            )

        finished_at = _now()
        if not self._emit(
            _succeeded_event(
                stage=stage,
                attempt_no=attempt_no,
                request=repair_request,
                response=response,
                prompt_version=self._engine._prompts[stage].version,
                engine=self._engine,
                started_at=started_at,
                finished_at=finished_at,
                latency_ms=_duration_ms(started_at, finished_at),
            )
        ):
            return self._sink_failure(stage)

        outcome = validate_response(response.content)
        if not outcome.ok:
            detail = outcome.errors[0].message if outcome.errors else None
            return self._fail_stage(
                stage,
                AnalysisErrorCode.MODEL_OUTPUT_INVALID,
                attempts_exhausted=True,
                error_detail=detail,
            )
        return self._accept_stage_result(stage, contract_version, outcome)

    def _accept_stage_result(
        self,
        stage: AnalysisStage,
        contract_version: str,
        outcome: StageValidationOutcome,
    ) -> Any:
        validated_result = outcome.result
        if validated_result is None:
            raise RuntimeError("校验器返回成功状态时必须携带阶段结果")
        if not self._emit(
            StageResultValidatedEvent(
                event_type="STAGE_RESULT_VALIDATED",
                stage=stage,
                contract_version=contract_version,
                result=validated_result,
            )
        ):
            return self._sink_failure(stage)
        return validated_result

    def _interrupt_before(self, stage: AnalysisStage) -> AnalysisFailure:
        if not self._emit(
            AnalysisCompletedEvent(
                event_type="ANALYSIS_COMPLETED",
                status="FAILED",
                finished_at=_now(),
                error_stage=stage,
                error_code=AnalysisErrorCode.APP_INTERRUPTED,
            )
        ):
            return self._sink_failure(stage)
        return _failure(
            self._request.trace_id,
            AnalysisErrorCode.APP_INTERRUPTED,
            stage,
            attempts_exhausted=False,
        )

    def _emit(self, event: AnalysisEvent) -> bool:
        """返回 False 表示出口持久化失败，必须立即停止当前案例。"""

        try:
            self._sink.emit(event)
        except Exception:
            return False
        return True

    def _sink_failure(self, stage: AnalysisStage) -> AnalysisFailure:
        return _failure(
            self._request.trace_id,
            AnalysisErrorCode.EVENT_SINK_FAILED,
            stage,
            attempts_exhausted=False,
        )

    def _fail_stage(
        self,
        stage: AnalysisStage,
        error_code: AnalysisErrorCode,
        *,
        attempts_exhausted: bool,
        error_detail: str | None = None,
    ) -> AnalysisFailure:
        if not self._emit(
            StageFailedEvent(
                event_type="STAGE_FAILED",
                stage=stage,
                error_code=error_code,
                error_detail=error_detail,
            )
        ):
            return _failure(
                self._request.trace_id,
                AnalysisErrorCode.EVENT_SINK_FAILED,
                stage,
                attempts_exhausted=attempts_exhausted,
            )
        if not self._emit(
            AnalysisCompletedEvent(
                event_type="ANALYSIS_COMPLETED",
                status="FAILED",
                finished_at=_now(),
                error_stage=stage,
                error_code=error_code,
            )
        ):
            return _failure(
                self._request.trace_id,
                AnalysisErrorCode.EVENT_SINK_FAILED,
                stage,
                attempts_exhausted=attempts_exhausted,
            )
        return _failure(
            self._request.trace_id, error_code, stage, attempts_exhausted=attempts_exhausted
        )


def _failure(
    trace_id: str,
    error_code: AnalysisErrorCode,
    error_stage: AnalysisStage,
    *,
    attempts_exhausted: bool,
) -> AnalysisFailure:
    return AnalysisFailure(
        status="FAILED",
        error_code=error_code,
        error_stage=error_stage,
        attempts_exhausted=attempts_exhausted,
        trace_id=trace_id,
    )


def _attempt_event(
    *,
    stage: AnalysisStage,
    attempt_no: int,
    attempt: Any,
    prompt_version: str,
    engine: AnalysisEngine,
    started_at: datetime,
    finished_at: datetime,
) -> ModelAttemptFinishedEvent:
    if attempt.response is not None:
        return _succeeded_event(
            stage=stage,
            attempt_no=attempt_no,
            request=attempt.request,
            response=attempt.response,
            prompt_version=prompt_version,
            engine=engine,
            started_at=started_at,
            finished_at=finished_at,
            latency_ms=attempt.latency_ms,
        )
    return _failed_event_from_parts(
        stage=stage,
        attempt_no=attempt_no,
        model_name=_model_name_of(attempt.request_manifest),
        prompt_version=prompt_version,
        started_at=started_at,
        finished_at=finished_at,
        request_manifest=attempt.request_manifest,
        error_code=attempt.error_code,
        error_summary=attempt.error_summary,
        latency_ms=attempt.latency_ms,
    )


def _failed_attempt_event(
    *,
    stage: AnalysisStage,
    attempt_no: int,
    request: GlmRequest,
    error: GlmClientError,
    prompt_version: str,
    engine: AnalysisEngine,
    started_at: datetime,
    finished_at: datetime,
) -> ModelAttemptFinishedEvent:
    return _failed_event_from_parts(
        stage=stage,
        attempt_no=attempt_no,
        model_name=engine._params.model_name,
        prompt_version=prompt_version,
        started_at=started_at,
        finished_at=finished_at,
        request_manifest=_manifest_for(engine, request),
        error_code=error.error_code,
        error_summary=error.detail,
        latency_ms=None,
    )


def _succeeded_event(
    *,
    stage: AnalysisStage,
    attempt_no: int,
    request: GlmRequest,
    response: Any,
    prompt_version: str,
    engine: AnalysisEngine,
    started_at: datetime,
    finished_at: datetime,
    latency_ms: int | None,
) -> ModelAttemptFinishedEvent:
    response_json: dict[str, Any] | None = None
    try:
        parsed = json.loads(response.content)
        response_json = (
            parsed if isinstance(parsed, dict) else {"raw_content": response.content}
        )
    except (ValueError, TypeError):
        response_json = {"raw_content": response.content}
    return ModelAttemptFinishedEvent(
        event_type="MODEL_ATTEMPT_FINISHED",
        stage=stage,
        attempt_no=attempt_no,
        model_name=engine._params.model_name,
        prompt_version=prompt_version,
        status="SUCCEEDED",
        started_at=started_at,
        finished_at=finished_at,
        latency_ms=latency_ms,
        prompt_tokens=response.prompt_tokens,
        completion_tokens=response.completion_tokens,
        total_tokens=response.total_tokens,
        request_manifest=_manifest_for(engine, request),
        response_json=response_json,
    )


def _failed_event_from_parts(
    *,
    stage: AnalysisStage,
    attempt_no: int,
    model_name: str,
    prompt_version: str,
    started_at: datetime,
    finished_at: datetime,
    request_manifest: dict[str, Any],
    error_code: AnalysisErrorCode | None,
    error_summary: str | None,
    latency_ms: int | None,
) -> ModelAttemptFinishedEvent:
    return ModelAttemptFinishedEvent(
        event_type="MODEL_ATTEMPT_FINISHED",
        stage=stage,
        attempt_no=attempt_no,
        model_name=model_name,
        prompt_version=prompt_version,
        status="FAILED",
        started_at=started_at,
        finished_at=finished_at,
        latency_ms=latency_ms,
        request_manifest=request_manifest,
        error_code=error_code,
        error_summary=error_summary,
    )


def _model_name_of(request_manifest: dict[str, Any]) -> str:
    model = request_manifest.get("model") if request_manifest else None
    return model if isinstance(model, str) else "glm-5.3-flash"


def _manifest_for(engine: AnalysisEngine, request: GlmRequest) -> dict[str, Any]:
    return build_request_manifest(
        request,
        params=engine._params,
        connect_timeout_seconds=engine._connect_timeout,
        response_timeout_seconds=engine._response_timeout,
    )


def _build_repair_request(
    last_request: GlmRequest | None, errors: tuple[StageValidationError, ...]
) -> GlmRequest:
    if last_request is None:
        raise RuntimeError("修复请求缺少原始请求")
    lines = [_REPAIR_NOTE_HEADER]
    lines.extend(
        f"- [{error.code.value}] {error.field_path}: {error.message}" for error in errors
    )
    lines.append(_REPAIR_NOTE_TAIL)
    return GlmRequest(
        stage=last_request.stage,
        prompt_version=last_request.prompt_version,
        system_prompt=last_request.system_prompt,
        user_content="\n".join([last_request.user_content, "", *lines]),
        images=last_request.images,
    )


def _evidence_content(case: CaseInput) -> dict[str, str]:
    """获准证据内容：脱敏对话与已核验订单事实（排除付款金额与高价值事实）。"""

    content: dict[str, str] = {}
    for item in sorted(case.evidence.text_items, key=lambda text: text.sequence_no):
        content[item.evidence_id] = f"（{item.role.value}）{item.text}"
    for item in case.evidence.behavior_items:
        if item.fact_type in (
            BehaviorFactType.ORDER_PAYMENT_TOTAL,
            BehaviorFactType.HIGH_VALUE_CUSTOMER,
        ):
            continue
        content[item.evidence_id] = f"{item.fact_type.value}: {item.value}"
    return content


def _case_allowed_ids(case: CaseInput) -> frozenset[str]:
    """案例级允许证据编号：全部证据（跨阶段引用由上游引用集合二次过滤）。"""

    return frozenset(
        {item.evidence_id for item in case.evidence.text_items}
        | {item.evidence_id for item in case.evidence.image_items}
        | {item.evidence_id for item in case.evidence.behavior_items}
    )


def _now() -> datetime:
    return datetime.now(UTC)


def _duration_ms(started_at: datetime, finished_at: datetime) -> int:
    return max(0, int((finished_at - started_at).total_seconds() * 1000))
