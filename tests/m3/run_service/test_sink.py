"""M3-05 RunStoreEventSink：M2 事件按序转发到 M1 RunStore（规格 9.1）。"""

from __future__ import annotations

from datetime import UTC, datetime

from run_fakes import FakeRunStore, make_success

from app.contracts.analysis import (
    AnalysisStage,
    ModelAttemptFinishedEvent,
    StageResultValidatedEvent,
    StageStartedEvent,
)
from app.modules.application.run_service.sink import RunStoreEventSink


def _now() -> datetime:
    return datetime(2026, 9, 7, 9, 0, 0, tzinfo=UTC)


def test_events_forward_in_order(run_store: FakeRunStore) -> None:
    case_run_id = 1
    sink = RunStoreEventSink(run_store, case_run_id)
    success = make_success("c1")

    sink.emit(
        StageStartedEvent(
            event_type="STAGE_STARTED",
            stage=AnalysisStage.PERCEPTION,
            started_at=_now(),
        )
    )
    sink.emit(
        ModelAttemptFinishedEvent(
            event_type="MODEL_ATTEMPT_FINISHED",
            stage=AnalysisStage.PERCEPTION,
            attempt_no=1,
            model_name="glm-5.3-flash",
            prompt_version="v1",
            status="SUCCEEDED",
            started_at=_now(),
            finished_at=_now(),
            latency_ms=42,
            total_tokens=10,
            request_manifest={"manifest_version": "v1"},
            response_json={"ok": True},
        )
    )
    sink.emit(
        StageResultValidatedEvent(
            event_type="STAGE_RESULT_VALIDATED",
            stage=AnalysisStage.PERCEPTION,
            contract_version="v1",
            result=success.perception,
        )
    )

    ordered = [
        c
        for c in run_store.calls
        if c.startswith(("stage_started", "model_attempt", "stage_result"))
    ]
    assert ordered == [
        "stage_started:1:perception",
        "model_attempt:1",
        "stage_result:1:perception",
    ]


def test_model_attempt_call_id_is_stable_per_run_and_unique_across_runs(
    run_store: FakeRunStore,
) -> None:
    event = ModelAttemptFinishedEvent(
        event_type="MODEL_ATTEMPT_FINISHED",
        stage=AnalysisStage.STRATEGY,
        attempt_no=2,
        model_name="glm-5.3-flash",
        prompt_version="v1",
        status="SUCCEEDED",
        started_at=_now(),
        finished_at=_now(),
        request_manifest={},
        response_json={"ok": True},
    )

    RunStoreEventSink(run_store, 1).emit(event)
    RunStoreEventSink(run_store, 1).emit(event)
    RunStoreEventSink(run_store, 2).emit(event)

    call_ids = [attempt.call_id for _, attempt in run_store.model_attempts]
    assert call_ids[0] == call_ids[1]
    assert call_ids[0] != call_ids[2]
