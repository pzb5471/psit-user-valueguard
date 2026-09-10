"""M3-05 RunService：批次开始、单一执行器与案例状态机编排（规格 9/10）。

职责边界（规格 8/10.2）：M3 决定状态转换与发布，M1 RunStore 在一个短事务内
原子写入，M2 AnalysisEngine 负责分析。RunService 只依赖端口协议，不碰 M1/M2
实现与 Session。状态决定归 M3、数据原子写入归 M1、分析职责归 M2。
"""

from __future__ import annotations

import hashlib
import json
import uuid
from concurrent.futures import ThreadPoolExecutor

from app.contracts.analysis import (
    AnalysisErrorCode,
    AnalysisFailure,
    AnalysisRequest,
    AnalysisSuccess,
)
from app.contracts.states import (
    BatchRunStatus,
    BatchStatus,
    CaseStatus,
    TriggerType,
)
from app.modules.application.api.contracts.errors import (
    ApiErrorCode,
    CaseProcessingErrorCode,
)
from app.modules.application.api.contracts.views import BatchWorkspaceView, CaseDetailView
from app.modules.application.run_service.ports import (
    AnalysisEnginePort,
    RunQueryPort,
    RunStorePort,
)
from app.modules.application.run_service.sink import RunStoreEventSink
from app.modules.application.run_service.versions import AnalysisVersionConfig
from app.modules.application.services.query import mapper
from app.modules.application.services.query.errors import ServiceError
from app.modules.data.run_store.errors import ActiveRunConflictError
from app.modules.data.run_store.types import StageResultInput

#: M2 稳定错误码 → M1 对外 processing_error 十类码（规格 12.4）。
_M2_TO_PROCESSING: dict[AnalysisErrorCode, CaseProcessingErrorCode] = {
    AnalysisErrorCode.MODEL_TIMEOUT: CaseProcessingErrorCode.MODEL_TIMEOUT,
    AnalysisErrorCode.MODEL_RATE_LIMITED: CaseProcessingErrorCode.MODEL_RATE_LIMITED,
    AnalysisErrorCode.MODEL_AUTH_REJECTED: CaseProcessingErrorCode.MODEL_AUTH_FAILED,
    AnalysisErrorCode.MODEL_OUTPUT_INVALID: CaseProcessingErrorCode.MODEL_RESPONSE_INVALID,
    AnalysisErrorCode.MODEL_REQUEST_INVALID: CaseProcessingErrorCode.MODEL_RESPONSE_INVALID,
    AnalysisErrorCode.INPUT_CONTRACT_INVALID: CaseProcessingErrorCode.EVIDENCE_MEDIA_INVALID,
    AnalysisErrorCode.EVENT_SINK_FAILED: CaseProcessingErrorCode.RESULT_PERSISTENCE_FAILED,
    AnalysisErrorCode.APP_INTERRUPTED: CaseProcessingErrorCode.APP_INTERRUPTED,
}


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


class RunService:
    """单实例运行服务；创建单一 ThreadPoolExecutor（规格 10.1）。"""

    def __init__(
        self,
        *,
        run_store: RunStorePort,
        analysis_engine: AnalysisEnginePort,
        query: RunQueryPort,
        versions: AnalysisVersionConfig,
        max_concurrency: int,
        analysis_available: bool = True,
        analysis_unavailable_message: str | None = None,
    ) -> None:
        self._run_store = run_store
        self._engine = analysis_engine
        self._query = query
        self._versions = versions
        self._analysis_available = analysis_available
        self._analysis_unavailable_message = analysis_unavailable_message
        self._executor = ThreadPoolExecutor(max_workers=max_concurrency)

    def _require_analysis_available(self) -> None:
        if self._analysis_available:
            return
        raise ServiceError(
            ApiErrorCode.ANALYSIS_UNAVAILABLE,
            self._analysis_unavailable_message or "分析服务当前不可用",
            next_action="完成真实分析引擎装配后重试",
        )

    def close(self) -> None:
        """正常关闭：等待在途案例完成后释放执行器（规格 10.6）。"""
        self._executor.shutdown(wait=True, cancel_futures=False)

    # ---------- 批次开始（规格 10.1/10.3） ----------

    def start_batch_run(self, batch_id: str) -> BatchWorkspaceView:
        try:
            projection = self._query.get_batch(batch_id)
        except LookupError:
            raise ServiceError(
                ApiErrorCode.RESOURCE_NOT_FOUND,
                f"批次不存在：{batch_id}",
                object_type="batch",
                object_id=batch_id,
            ) from None

        self._require_analysis_available()

        # 幂等：批次已在分析中，重复开始返回当前视图（规格 10.1 一个活动批次）。
        if projection.status == BatchStatus.ANALYZING.value:
            return mapper.to_batch_workspace(projection)

        batch_run_id = _new_id("BR")
        try:
            batch_run = self._run_store.create_batch_run(
                batch_id=batch_id,
                run_id=batch_run_id,
                total_case_count=projection.case_count,
            )
        except ActiveRunConflictError as error:
            raise ServiceError(
                ApiErrorCode.ACTIVE_BATCH_EXISTS,
                "已有首次批量分析正在运行",
                object_type="batch",
                object_id=batch_id,
            ) from error

        case_queue = self._query.list_cases(batch_id, limit=100)
        for item in case_queue.items:
            case_run = self._run_store.create_case_run(
                batch_id=batch_id,
                case_id=item.case_id,
                run_id=_new_id("CR"),
                trigger_type=TriggerType.BATCH,
                batch_run_id=batch_run.run_id,
            )
            self._executor.submit(
                self._run_case,
                batch_id,
                item.case_id,
                case_run.id,
                batch_run.id,
            )
        return mapper.to_batch_workspace(self._query.get_batch(batch_id))

    # ---------- 单案例重跑（状态机：规格 10.2/10.3） ----------

    def rerun_case(self, batch_id: str, case_id: str) -> CaseDetailView:
        """待确认或异常案例从头重跑；PENDING_ANALYSIS/COMPLETED 禁止（规格 10.2）。"""
        try:
            detail = self._query.get_case_detail(batch_id, case_id)
        except LookupError:
            raise ServiceError(
                ApiErrorCode.RESOURCE_NOT_FOUND,
                f"案例不存在：{batch_id}/{case_id}",
                object_type="case",
                object_id=case_id,
            ) from None
        self._require_analysis_available()
        if detail.status in (
            CaseStatus.PENDING_ANALYSIS.value,
            CaseStatus.COMPLETED.value,
        ):
            code = (
                ApiErrorCode.CASE_NOT_RERUNNABLE
                if detail.status == CaseStatus.PENDING_ANALYSIS.value
                else ApiErrorCode.CASE_ALREADY_COMPLETED
            )
            raise ServiceError(
                code,
                f"当前案例状态不允许重跑：{detail.status}",
                object_type="case",
                object_id=case_id,
            )
        try:
            case_run = self._run_store.create_case_run(
                batch_id=batch_id,
                case_id=case_id,
                run_id=_new_id("CR"),
                trigger_type=TriggerType.MANUAL_RERUN,
                batch_run_id=None,
            )
        except ActiveRunConflictError as error:
            raise ServiceError(
                ApiErrorCode.ACTIVE_CASE_RUN_EXISTS,
                "同一案例已有活动运行",
                object_type="case",
                object_id=case_id,
            ) from error
        self._executor.submit(self._run_case, batch_id, case_id, case_run.id, None)
        return mapper.to_case_detail(self._query.get_case_detail(batch_id, case_id))

    # ---------- 单案例执行（状态机：规格 10.2） ----------

    def _run_case(
        self, batch_id: str, case_id: str, case_run_id: int, batch_run_id: int | None
    ) -> None:
        try:
            case_input = self._query.get_case_input(batch_id, case_id)
            if case_input is None:
                self._record_failure(case_run_id, "INPUT_CONTRACT_INVALID", "INPUT_PREPARATION")
                return
            request = AnalysisRequest(
                trace_id=_new_id("trace"),
                case_run_id=case_run_id,
                case_input=case_input,
                perception_contract_version=self._versions.perception_contract_version,
                attribution_contract_version=self._versions.attribution_contract_version,
                strategy_contract_version=self._versions.strategy_contract_version,
                perception_prompt_version=self._versions.perception_prompt_version,
                attribution_prompt_version=self._versions.attribution_prompt_version,
                strategy_prompt_version=self._versions.strategy_prompt_version,
                action_catalog_version=self._versions.action_catalog_version,
            )
            sink = RunStoreEventSink(self._run_store, case_run_id)
            outcome = self._engine.analyze_case(request, sink)
            if isinstance(outcome, AnalysisSuccess):
                self._publish(case_run_id, outcome)
            elif isinstance(outcome, AnalysisFailure):
                self._record_failure(
                    case_run_id,
                    _processing_code(outcome.error_code),
                    outcome.error_stage.value,
                )
        except ServiceError:
            raise
        except Exception:
            self._record_failure(case_run_id, "UNEXPECTED_PROCESSING_ERROR", "AI_ANALYSIS")
        finally:
            self._maybe_finish_batch(batch_id, batch_run_id)

    def _publish(self, case_run_id: int, outcome: AnalysisSuccess) -> None:
        decision = outcome.decision
        result_json = decision.model_dump(mode="json")
        final_stage = StageResultInput(
            stage_name="strategy",
            contract_version=self._versions.strategy_contract_version,
            result_json=result_json,
            result_sha256=_sha256(result_json),
        )
        self._run_store.publish_complete_result(
            case_run_id=case_run_id,
            final_stage=final_stage,
            system_intervention_level=decision.intervention_level.value,
        )

    def _record_failure(self, case_run_id: int, error_code: str, error_stage: str) -> None:
        self._run_store.record_failure(
            case_run_id=case_run_id,
            error_code=error_code,
            error_stage=error_stage,
        )

    # ---------- 批次结束判定（规格 10.3；MANUAL_RERUN 不改写首次批次历史） ----------

    def _maybe_finish_batch(self, batch_id: str, batch_run_id: int | None) -> None:
        if batch_run_id is None:
            return
        try:
            projection = self._query.get_batch(batch_id)
        except LookupError:
            return
        total = projection.case_count
        done = projection.analysis_succeeded_count + projection.error_count
        if total and done >= total:
            status = (
                BatchRunStatus.COMPLETED
                if projection.error_count == 0
                else BatchRunStatus.COMPLETED_WITH_ERRORS
            )
            self._run_store.finish_batch_run(batch_run_id=batch_run_id, status=status)


def _sha256(data: dict) -> str:
    return hashlib.sha256(
        json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _processing_code(error_code: AnalysisErrorCode) -> str:
    """把 M2 稳定错误码映射为 M1 对外 processing_error 码（规格 12.4 十类）。"""
    return _M2_TO_PROCESSING.get(
        error_code, CaseProcessingErrorCode.UNEXPECTED_PROCESSING_ERROR
    ).value
