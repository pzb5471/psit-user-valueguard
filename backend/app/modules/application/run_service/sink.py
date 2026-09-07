"""M2 分析事件 → M1 RunStore 的转发（M3-05；规格 9.1）。

M2 引擎按序发出五类事件；本 sink 把需要持久化的阶段事件转发给 M1 RunStore
的短事务命令（STAGE_STARTED / MODEL_ATTEMPT_FINISHED / STAGE_RESULT_VALIDATED）。
事件持久化失败时让异常传播，M2 据此立即停止当前案例（规格 9.1）。
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from app.contracts.analysis import (
    AnalysisEvent,
    AnalysisEventSink,
    AnalysisStage,
    ModelAttemptFinishedEvent,
    StageResultValidatedEvent,
    StageStartedEvent,
)
from app.contracts.states import CaseRunStatus
from app.modules.data.run_store.types import ModelAttemptInput, StageResultInput

_STAGE_NAME = {
    AnalysisStage.PERCEPTION: "perception",
    AnalysisStage.ATTRIBUTION: "attribution",
    AnalysisStage.STRATEGY: "strategy",
}

_STAGE_RUN_STATUS = {
    AnalysisStage.PERCEPTION: CaseRunStatus.PERCEPTION_RUNNING,
    AnalysisStage.ATTRIBUTION: CaseRunStatus.ATTRIBUTION_RUNNING,
    AnalysisStage.STRATEGY: CaseRunStatus.STRATEGY_RUNNING,
}


def _result_sha256(result_json: dict) -> str:
    return hashlib.sha256(
        json.dumps(result_json, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _utc_now() -> datetime:
    return datetime.now(UTC)


class RunStoreEventSink(AnalysisEventSink):
    """把 M2 事件转发到 M1 RunStore；持有一个内部 case_run_id。"""

    def __init__(self, run_store, case_run_id: int) -> None:
        self._run_store = run_store
        self._case_run_id = case_run_id

    def emit(self, event: AnalysisEvent) -> None:
        if isinstance(event, StageStartedEvent):
            self._run_store.record_stage_started(
                case_run_id=self._case_run_id,
                stage_name=_STAGE_NAME[event.stage],
                status=_STAGE_RUN_STATUS[event.stage],
                occurred_at=event.started_at,
            )
        elif isinstance(event, ModelAttemptFinishedEvent):
            self._run_store.record_model_attempt(
                case_run_id=self._case_run_id,
                attempt=self._attempt(event),
            )
        elif isinstance(event, StageResultValidatedEvent):
            self._run_store.record_stage_result(
                case_run_id=self._case_run_id,
                stage=self._stage_result(event),
                occurred_at=_utc_now(),
            )
        # StageFailedEvent / AnalysisCompletedEvent 由最终 AnalysisOutcome 驱动，
        # 不在此单独持久化，避免重复记录。

    @staticmethod
    def _attempt(event: ModelAttemptFinishedEvent) -> ModelAttemptInput:
        call_id = f"{event.stage.value}:{event.attempt_no}"
        error_json: dict | None = None
        if event.status == "FAILED":
            error_json = {
                "error_code": event.error_code.value if event.error_code else "UNKNOWN",
                "error_summary": event.error_summary,
            }
        return ModelAttemptInput(
            call_id=call_id,
            stage_name=_STAGE_NAME[event.stage],
            attempt_no=event.attempt_no,
            model_name=event.model_name,
            prompt_version=event.prompt_version,
            request_manifest_json=event.request_manifest,
            status=event.status,
            response_json=event.response_json,
            error_json=error_json,
            started_at=event.started_at,
            finished_at=event.finished_at,
            latency_ms=event.latency_ms,
            prompt_token_count=event.prompt_tokens,
            completion_token_count=event.completion_tokens,
            total_token_count=event.total_tokens,
        )

    @staticmethod
    def _stage_result(event: StageResultValidatedEvent) -> StageResultInput:
        result_json = event.result.model_dump(mode="json")
        return StageResultInput(
            stage_name=_STAGE_NAME[event.stage],
            contract_version=event.contract_version,
            result_json=result_json,
            result_sha256=_result_sha256(result_json),
        )
