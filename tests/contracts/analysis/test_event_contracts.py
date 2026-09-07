"""M2-01 合同验收：五类分析事件与事件出口协议（规格第 9.1、9.3 节）。

AnalysisEventSink 依次接收 STAGE_STARTED、MODEL_ATTEMPT_FINISHED、
STAGE_RESULT_VALIDATED、STAGE_FAILED、ANALYSIS_COMPLETED 五类事件；
事件用于 M3 调用 M1 保存运行记录（model_calls、stage_results 所需字段）。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest
from analysis_samples import attribution_result, decision_package, perception_result
from pydantic import TypeAdapter, ValidationError

from app.contracts.analysis import (
    AnalysisErrorCode,
    AnalysisEvent,
    AnalysisEventSink,
    AnalysisStage,
    AttributionResult,
    DecisionPackage,
    PerceptionResult,
)

pytestmark = pytest.mark.task_m2_01

EVENT_ADAPTER = TypeAdapter(AnalysisEvent)
NOW = datetime(2026, 9, 6, 8, 0, 0, tzinfo=UTC)


def event_json(sample: dict[str, Any]) -> str:
    return json.dumps(sample, ensure_ascii=False)


def stage_started(**overrides: Any) -> dict[str, Any]:
    sample: dict[str, Any] = {
        "event_type": "STAGE_STARTED",
        "stage": "PERCEPTION",
        "started_at": NOW.isoformat(),
    }
    sample.update(overrides)
    return sample


def attempt_finished(**overrides: Any) -> dict[str, Any]:
    sample: dict[str, Any] = {
        "event_type": "MODEL_ATTEMPT_FINISHED",
        "stage": "PERCEPTION",
        "attempt_no": 1,
        "model_name": "glm-5.3-flash",
        "prompt_version": "v1",
        "status": "SUCCEEDED",
        "started_at": NOW.isoformat(),
        "finished_at": NOW.isoformat(),
        "latency_ms": 1234,
        "request_manifest": {"messages": ["感知阶段请求清单"]},
        "response_json": {"choices": []},
    }
    sample.update(overrides)
    return sample


def result_validated(**overrides: Any) -> dict[str, Any]:
    sample: dict[str, Any] = {
        "event_type": "STAGE_RESULT_VALIDATED",
        "stage": "PERCEPTION",
        "contract_version": "v1",
        "result": perception_result(),
    }
    sample.update(overrides)
    return sample


def stage_failed(**overrides: Any) -> dict[str, Any]:
    sample: dict[str, Any] = {
        "event_type": "STAGE_FAILED",
        "stage": "PERCEPTION",
        "error_code": "MODEL_TIMEOUT",
        "error_detail": "读取超时，已耗尽允许尝试。",
    }
    sample.update(overrides)
    return sample


def analysis_completed(**overrides: Any) -> dict[str, Any]:
    sample: dict[str, Any] = {
        "event_type": "ANALYSIS_COMPLETED",
        "status": "SUCCESS",
        "finished_at": NOW.isoformat(),
    }
    sample.update(overrides)
    return sample


class TestFiveEventTypes:
    @pytest.mark.parametrize(
        ("builder", "event_type"),
        [
            (stage_started, "STAGE_STARTED"),
            (attempt_finished, "MODEL_ATTEMPT_FINISHED"),
            (result_validated, "STAGE_RESULT_VALIDATED"),
            (stage_failed, "STAGE_FAILED"),
            (analysis_completed, "ANALYSIS_COMPLETED"),
        ],
    )
    def test_each_event_type_round_trips(self, builder, event_type: str) -> None:
        event = EVENT_ADAPTER.validate_json(event_json(builder()))
        assert event.event_type == event_type

    def test_rejects_unknown_event_type(self) -> None:
        with pytest.raises(ValidationError):
            EVENT_ADAPTER.validate_json(event_json(stage_started(event_type="STAGE_PAUSED")))

    def test_rejects_extra_field(self) -> None:
        with pytest.raises(ValidationError):
            EVENT_ADAPTER.validate_json(event_json(stage_started(probability=0.5)))

    def test_rejects_naive_timestamp_without_timezone(self) -> None:
        naive = datetime(2026, 9, 6, 8, 0, 0).isoformat()
        with pytest.raises(ValidationError):
            EVENT_ADAPTER.validate_json(event_json(stage_started(started_at=naive)))

    def test_rejects_non_utc_timestamp(self) -> None:
        with pytest.raises(ValidationError):
            EVENT_ADAPTER.validate_json(
                event_json(stage_started(started_at="2026-09-06T16:00:00+08:00"))
            )


class TestModelAttemptEvent:
    def test_optional_token_and_error_fields_are_omitted_when_not_applicable(self) -> None:
        event = EVENT_ADAPTER.validate_json(event_json(attempt_finished()))
        assert event.prompt_tokens is None
        assert event.error_code is None

    def test_token_counts_must_be_non_negative(self) -> None:
        sample = attempt_finished(prompt_tokens=-1)
        with pytest.raises(ValidationError):
            EVENT_ADAPTER.validate_json(event_json(sample))

    def test_attempt_number_must_be_positive(self) -> None:
        sample = attempt_finished(attempt_no=0)
        with pytest.raises(ValidationError):
            EVENT_ADAPTER.validate_json(event_json(sample))

    def test_status_only_allows_succeeded_or_failed(self) -> None:
        sample = attempt_finished(status="OK")
        with pytest.raises(ValidationError):
            EVENT_ADAPTER.validate_json(event_json(sample))

    def test_failed_attempt_carries_stable_error_code(self) -> None:
        sample = attempt_finished(
            status="FAILED",
            response_json=None,
            error_code="MODEL_RATE_LIMITED",
            error_summary="供应商返回 429。",
        )
        event = EVENT_ADAPTER.validate_json(event_json(sample))
        assert event.error_code == AnalysisErrorCode.MODEL_RATE_LIMITED

    @pytest.mark.parametrize(
        "sample",
        [
            attempt_finished(error_code="MODEL_TIMEOUT", error_summary="超时"),
            attempt_finished(response_json=None),
            attempt_finished(
                status="FAILED",
                response_json={"unexpected": True},
                error_code="MODEL_TIMEOUT",
                error_summary="超时",
            ),
            attempt_finished(status="FAILED", response_json=None),
        ],
    )
    def test_response_and_error_fields_must_match_status(
        self, sample: dict[str, Any]
    ) -> None:
        with pytest.raises(ValidationError):
            EVENT_ADAPTER.validate_json(event_json(sample))

    def test_finished_at_cannot_precede_started_at(self) -> None:
        sample = attempt_finished(finished_at="2026-09-06T07:59:59+00:00")
        with pytest.raises(ValidationError):
            EVENT_ADAPTER.validate_json(event_json(sample))

    def test_request_manifest_is_required(self) -> None:
        sample = attempt_finished()
        del sample["request_manifest"]
        with pytest.raises(ValidationError):
            EVENT_ADAPTER.validate_json(event_json(sample))


class TestStageResultValidatedEvent:
    def test_carries_perception_result(self) -> None:
        event = EVENT_ADAPTER.validate_json(event_json(result_validated()))
        assert isinstance(event.result, PerceptionResult)
        assert event.result.case_id == "case-0001"

    def test_carries_attribution_result(self) -> None:
        sample = result_validated(stage="ATTRIBUTION", result=attribution_result())
        event = EVENT_ADAPTER.validate_json(event_json(sample))
        assert isinstance(event.result, AttributionResult)

    def test_carries_decision_package(self) -> None:
        sample = result_validated(stage="STRATEGY", result=decision_package())
        event = EVENT_ADAPTER.validate_json(event_json(sample))
        assert isinstance(event.result, DecisionPackage)

    def test_rejects_result_outside_three_contracts(self) -> None:
        sample = result_validated(result={"nonsense": True})
        with pytest.raises(ValidationError):
            EVENT_ADAPTER.validate_json(event_json(sample))

    def test_stage_must_match_result_contract(self) -> None:
        sample = result_validated(stage="STRATEGY", result=perception_result())
        with pytest.raises(ValidationError):
            EVENT_ADAPTER.validate_json(event_json(sample))


class TestAnalysisCompletedEvent:
    def test_success_event_forbids_error_fields(self) -> None:
        sample = analysis_completed(error_stage="PERCEPTION", error_code="MODEL_TIMEOUT")
        with pytest.raises(ValidationError):
            EVENT_ADAPTER.validate_json(event_json(sample))

    def test_failure_event_requires_error_fields(self) -> None:
        sample = analysis_completed(status="FAILED")
        with pytest.raises(ValidationError):
            EVENT_ADAPTER.validate_json(event_json(sample))

    def test_failure_event_with_error_fields_is_accepted(self) -> None:
        sample = analysis_completed(
            status="FAILED",
            error_stage="STRATEGY",
            error_code="MODEL_OUTPUT_INVALID",
        )
        event = EVENT_ADAPTER.validate_json(event_json(sample))
        assert event.error_stage == AnalysisStage.STRATEGY


class TestAnalysisEventSinkProtocol:
    def test_object_with_emit_satisfies_protocol(self) -> None:
        class RecordingSink:
            def __init__(self) -> None:
                self.received: list[Any] = []

            def emit(self, event: Any) -> None:
                self.received.append(event)

        assert isinstance(RecordingSink(), AnalysisEventSink)

    def test_object_without_emit_does_not_satisfy_protocol(self) -> None:
        class NotASink:
            pass

        assert not isinstance(NotASink(), AnalysisEventSink)
