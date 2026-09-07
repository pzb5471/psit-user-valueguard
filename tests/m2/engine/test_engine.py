"""M2-08 验收：AnalysisEngine 编排、有界重试、一次修复与事件序列（规格第 9 节）。

面向唯一公开入口 analyze_case 验证：合法事件顺序、网络重试、不可重试错误、
一次定向修复、修复请求网络失败、每阶段请求上限、事件保存失败立即停止、
阶段边界关闭（失败后不进入后续阶段）与关闭检查。
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from engine_samples import (
    CASE_ID,
    TRACE_ID,
    attribution_json,
    broken_perception_json,
    loaded_case_input,
    loaded_case_input_with_image,
    perception_json,
    strategy_json,
)

from app.contracts.analysis import (
    AnalysisErrorCode,
    AnalysisFailure,
    AnalysisRequest,
    AnalysisStage,
    AnalysisSuccess,
)
from app.modules.analysis.client import GlmClientError, GlmResponse, ScriptedGlmClient
from app.modules.analysis.engine import AnalysisEngine
from app.modules.analysis.strategy import ActionCatalogEntry, ActionCatalogView

pytestmark = pytest.mark.task_m2_08

CATALOG = ActionCatalogView(
    catalog_version="v1",
    actions=(
        ActionCatalogEntry(action_type="EVIDENCE_CHECK", description="补充或核实证据"),
        ActionCatalogEntry(action_type="CUSTOMER_CONTACT", description="人工联系客户"),
        ActionCatalogEntry(action_type="FULFILLMENT_ESCALATION", description="升级履约处理"),
        ActionCatalogEntry(
            action_type="REPLACEMENT_RETURN_REFUND_CHECK", description="退货退款核验"
        ),
        ActionCatalogEntry(
            action_type="APOLOGY_COMPENSATION_RETENTION_REQUEST", description="道歉补偿挽留申请"
        ),
        ActionCatalogEntry(action_type="NO_ACTION_MONITOR", description="暂不动作并观察"),
    ),
)


class FakeEventSink:
    """记录全部事件；可指定在某类事件上模拟持久化失败。"""

    def __init__(self, fail_on: str | None = None) -> None:
        self.events: list[Any] = []
        self.fail_on = fail_on

    def emit(self, event: Any) -> None:
        if self.fail_on is not None and event.event_type == self.fail_on:
            raise RuntimeError("事件持久化失败（模拟）")
        self.events.append(event)

    def types(self) -> list[str]:
        return [event.event_type for event in self.events]


def make_engine(
    client: ScriptedGlmClient,
    *,
    image_data_resolver=None,
    shutdown_requested=None,
) -> AnalysisEngine:
    return AnalysisEngine(
        model_client=client,
        image_data_resolver=image_data_resolver
        or (lambda _path: (_ for _ in ()).throw(FileNotFoundError(_path))),
        action_catalog=CATALOG,
        shutdown_requested=shutdown_requested,
    )


def make_request(case_input: Any = None) -> AnalysisRequest:
    return AnalysisRequest(
        trace_id=TRACE_ID,
        case_run_id=1,
        case_input=case_input if case_input is not None else loaded_case_input(),
        perception_contract_version="v1",
        attribution_contract_version="v1",
        strategy_contract_version="v1",
        perception_prompt_version="v1",
        attribution_prompt_version="v1",
        strategy_prompt_version="v1",
        action_catalog_version="v1",
    )


def happy_script() -> list[Any]:
    return [
        GlmResponse(content=perception_json()),
        GlmResponse(content=attribution_json()),
        GlmResponse(content=strategy_json()),
    ]


class TestHappyPath:
    def test_event_sequence_and_success(self) -> None:
        client = ScriptedGlmClient(happy_script())
        sink = FakeEventSink()
        engine = make_engine(client)

        outcome = engine.analyze_case(make_request(), sink)

        assert isinstance(outcome, AnalysisSuccess)
        assert outcome.perception.case_id == CASE_ID
        assert outcome.decision.intervention_level is not None
        assert len(client.requests) == 3
        assert sink.types() == [
            "STAGE_STARTED",
            "MODEL_ATTEMPT_FINISHED",
            "STAGE_RESULT_VALIDATED",
            "STAGE_STARTED",
            "MODEL_ATTEMPT_FINISHED",
            "STAGE_RESULT_VALIDATED",
            "STAGE_STARTED",
            "MODEL_ATTEMPT_FINISHED",
            "STAGE_RESULT_VALIDATED",
            "ANALYSIS_COMPLETED",
        ]
        assert sink.events[-1].status == "SUCCESS"

    def test_stages_run_in_frozen_order(self) -> None:
        client = ScriptedGlmClient(happy_script())
        sink = FakeEventSink()
        make_engine(client).analyze_case(make_request(), sink)

        started = [
            event.stage
            for event in sink.events
            if event.event_type == "STAGE_STARTED"
        ]
        assert started == [
            AnalysisStage.PERCEPTION,
            AnalysisStage.ATTRIBUTION,
            AnalysisStage.STRATEGY,
        ]


class TestBoundedRetry:
    def test_retryable_errors_retry_then_succeed(self) -> None:
        client = ScriptedGlmClient(
            [
                GlmClientError(AnalysisErrorCode.MODEL_TIMEOUT, "超时"),
                GlmClientError(AnalysisErrorCode.MODEL_NETWORK, "中断"),
                GlmResponse(content=perception_json()),
                GlmResponse(content=attribution_json()),
                GlmResponse(content=strategy_json()),
            ]
        )
        sink = FakeEventSink()

        outcome = make_engine(client).analyze_case(make_request(), sink)

        assert isinstance(outcome, AnalysisSuccess)
        assert len(client.requests) == 5
        perception_attempts = [
            event
            for event in sink.events
            if event.event_type == "MODEL_ATTEMPT_FINISHED"
            and event.stage is AnalysisStage.PERCEPTION
        ]
        assert [event.status for event in perception_attempts] == [
            "FAILED",
            "FAILED",
            "SUCCEEDED",
        ]

    def test_retry_exhaustion_fails_stage_and_stops(self) -> None:
        client = ScriptedGlmClient(
            [
                GlmClientError(AnalysisErrorCode.MODEL_TIMEOUT, "超时一"),
                GlmClientError(AnalysisErrorCode.MODEL_TIMEOUT, "超时二"),
                GlmClientError(AnalysisErrorCode.MODEL_TIMEOUT, "超时三"),
                GlmResponse(content=attribution_json()),
                GlmResponse(content=strategy_json()),
            ]
        )
        sink = FakeEventSink()

        outcome = make_engine(client).analyze_case(make_request(), sink)

        assert isinstance(outcome, AnalysisFailure)
        assert outcome.error_code is AnalysisErrorCode.MODEL_TIMEOUT
        assert outcome.error_stage is AnalysisStage.PERCEPTION
        assert outcome.attempts_exhausted is True
        assert len(client.requests) == 3
        assert "STAGE_FAILED" in sink.types()
        assert "STAGE_STARTED" in sink.types() and "ATTRIBUTION" not in str(
            [str(event.stage) for event in sink.events if event.event_type == "STAGE_STARTED"]
        )
        assert sink.events[-1].status == "FAILED"

    def test_non_retryable_error_fails_immediately(self) -> None:
        client = ScriptedGlmClient(
            [GlmClientError(AnalysisErrorCode.MODEL_AUTH_REJECTED, "密钥被拒")]
        )
        sink = FakeEventSink()

        outcome = make_engine(client).analyze_case(make_request(), sink)

        assert isinstance(outcome, AnalysisFailure)
        assert outcome.error_code is AnalysisErrorCode.MODEL_AUTH_REJECTED
        assert outcome.attempts_exhausted is False
        assert len(client.requests) == 1
        assert sink.events[-1].status == "FAILED"


class TestTargetedRepair:
    def test_one_repair_with_specific_errors(self) -> None:
        client = ScriptedGlmClient(
            [
                GlmResponse(content=broken_perception_json()),
                GlmResponse(content=perception_json()),
                GlmResponse(content=attribution_json()),
                GlmResponse(content=strategy_json()),
            ]
        )
        sink = FakeEventSink()

        outcome = make_engine(client).analyze_case(make_request(), sink)

        assert isinstance(outcome, AnalysisSuccess)
        assert len(client.requests) == 4
        repair_content = client.requests[1].user_content
        assert "上次输出未通过严格校验" in repair_content
        assert "emotion" in repair_content
        assert client.requests[1].system_prompt == client.requests[0].system_prompt
        perception_attempts = [
            event
            for event in sink.events
            if event.event_type == "MODEL_ATTEMPT_FINISHED"
            and event.stage is AnalysisStage.PERCEPTION
        ]
        assert [event.attempt_no for event in perception_attempts] == [1, 2]

    def test_nonrepairable_forbidden_content_fails_without_repair(self) -> None:
        poisoned = json.loads(perception_json())
        poisoned["events"][0]["summary"] = "key_answer 指定了结论。"
        client = ScriptedGlmClient(
            [
                GlmResponse(content=json.dumps(poisoned, ensure_ascii=False)),
                GlmResponse(content=perception_json()),
                GlmResponse(content=attribution_json()),
                GlmResponse(content=strategy_json()),
            ]
        )

        outcome = make_engine(client).analyze_case(make_request(), FakeEventSink())

        assert isinstance(outcome, AnalysisFailure)
        assert outcome.error_code is AnalysisErrorCode.MODEL_OUTPUT_INVALID
        assert outcome.attempts_exhausted is False
        assert len(client.requests) == 1

    def test_repair_response_still_enforces_image_coverage(self) -> None:
        client = ScriptedGlmClient(
            [
                GlmResponse(content=broken_perception_json()),
                GlmResponse(content=perception_json()),
            ]
        )
        engine = make_engine(
            client,
            image_data_resolver=lambda _path: ("image/jpeg", b"image-bytes"),
        )

        outcome = engine.analyze_case(
            make_request(loaded_case_input_with_image()), FakeEventSink()
        )

        assert isinstance(outcome, AnalysisFailure)
        assert outcome.error_code is AnalysisErrorCode.MODEL_OUTPUT_INVALID
        assert outcome.error_stage is AnalysisStage.PERCEPTION
        assert len(client.requests) == 2

    def test_repaired_strategy_still_applies_program_floor(self) -> None:
        broken_strategy = json.loads(strategy_json())
        del broken_strategy["actions"]
        repaired_strategy = json.loads(strategy_json())
        repaired_strategy["intervention_level"] = "NO_IMMEDIATE_INTERVENTION"
        client = ScriptedGlmClient(
            [
                GlmResponse(content=perception_json()),
                GlmResponse(content=attribution_json()),
                GlmResponse(content=json.dumps(broken_strategy, ensure_ascii=False)),
                GlmResponse(content=json.dumps(repaired_strategy, ensure_ascii=False)),
            ]
        )

        outcome = make_engine(client).analyze_case(make_request(), FakeEventSink())

        assert isinstance(outcome, AnalysisSuccess)
        assert outcome.decision.intervention_level.value == "SHOULD_INTERVENE"

    def test_repair_output_still_invalid_fails_once(self) -> None:
        client = ScriptedGlmClient(
            [
                GlmResponse(content=broken_perception_json()),
                GlmResponse(content=broken_perception_json()),
            ]
        )
        sink = FakeEventSink()

        outcome = make_engine(client).analyze_case(make_request(), sink)

        assert isinstance(outcome, AnalysisFailure)
        assert outcome.error_code is AnalysisErrorCode.MODEL_OUTPUT_INVALID
        assert outcome.attempts_exhausted is True
        assert len(client.requests) == 2
        assert sink.events[-1].status == "FAILED"

    def test_repair_network_failure_stops_without_more_retries(self) -> None:
        client = ScriptedGlmClient(
            [
                GlmResponse(content=broken_perception_json()),
                GlmClientError(AnalysisErrorCode.MODEL_TIMEOUT, "修复请求超时"),
            ]
        )
        sink = FakeEventSink()

        outcome = make_engine(client).analyze_case(make_request(), sink)

        assert isinstance(outcome, AnalysisFailure)
        assert outcome.error_code is AnalysisErrorCode.MODEL_TIMEOUT
        assert outcome.attempts_exhausted is True
        assert len(client.requests) == 2

    def test_repair_attempt_event_failure_stops_as_sink_failure(self) -> None:
        class SecondAttemptFailSink(FakeEventSink):
            def __init__(self) -> None:
                super().__init__()
                self.attempt_count = 0

            def emit(self, event: Any) -> None:
                if event.event_type == "MODEL_ATTEMPT_FINISHED":
                    self.attempt_count += 1
                    if self.attempt_count == 2:
                        raise RuntimeError("修复尝试事件保存失败（模拟）")
                super().emit(event)

        client = ScriptedGlmClient(
            [
                GlmResponse(content=broken_perception_json()),
                GlmClientError(AnalysisErrorCode.MODEL_TIMEOUT, "修复请求超时"),
            ]
        )

        outcome = make_engine(client).analyze_case(
            make_request(), SecondAttemptFailSink()
        )

        assert isinstance(outcome, AnalysisFailure)
        assert outcome.error_code is AnalysisErrorCode.EVENT_SINK_FAILED
        assert len(client.requests) == 2

    def test_request_cap_four_per_stage(self) -> None:
        client = ScriptedGlmClient(
            [
                GlmClientError(AnalysisErrorCode.MODEL_TIMEOUT, "超时一"),
                GlmClientError(AnalysisErrorCode.MODEL_TIMEOUT, "超时二"),
                GlmResponse(content=broken_perception_json()),
                GlmResponse(content=broken_perception_json()),
                GlmResponse(content=attribution_json()),
            ]
        )
        sink = FakeEventSink()

        outcome = make_engine(client).analyze_case(make_request(), sink)

        assert isinstance(outcome, AnalysisFailure)
        assert outcome.error_code is AnalysisErrorCode.MODEL_OUTPUT_INVALID
        assert len(client.requests) == 4


class TestSinkAndBoundaries:
    def test_event_sink_failure_stops_case_immediately(self) -> None:
        client = ScriptedGlmClient([GlmResponse(content=perception_json())])
        sink = FakeEventSink(fail_on="STAGE_RESULT_VALIDATED")

        outcome = make_engine(client).analyze_case(make_request(), sink)

        assert isinstance(outcome, AnalysisFailure)
        assert outcome.error_code is AnalysisErrorCode.EVENT_SINK_FAILED
        assert outcome.error_stage is AnalysisStage.PERCEPTION
        assert outcome.trace_id == TRACE_ID
        assert len(client.requests) == 1
        assert "STAGE_STARTED" in sink.types() and sink.types().count("STAGE_STARTED") == 1

    def test_stage_failure_never_enters_next_stage(self) -> None:
        client = ScriptedGlmClient(
            [
                GlmResponse(content=perception_json()),
                GlmClientError(AnalysisErrorCode.MODEL_AUTH_REJECTED, "密钥被拒"),
            ]
        )
        sink = FakeEventSink()

        make_engine(client).analyze_case(make_request(), sink)

        started = [
            event.stage.value
            for event in sink.events
            if event.event_type == "STAGE_STARTED"
        ]
        assert started == ["PERCEPTION", "ATTRIBUTION"]
        assert sink.events[-1].status == "FAILED"

    def test_close_is_idempotent_and_blocks_new_calls(self) -> None:
        client = ScriptedGlmClient(happy_script())
        engine = make_engine(client)
        engine.close()
        engine.close()

        with pytest.raises(RuntimeError, match="已关闭"):
            engine.analyze_case(make_request(), FakeEventSink())

    def test_close_after_current_stage_prevents_next_stage(self) -> None:
        shutdown = {"requested": False}

        class ClosingSink(FakeEventSink):
            def emit(self, event: Any) -> None:
                super().emit(event)
                if (
                    event.event_type == "STAGE_RESULT_VALIDATED"
                    and event.stage is AnalysisStage.PERCEPTION
                ):
                    shutdown["requested"] = True

        client = ScriptedGlmClient(happy_script())
        engine = make_engine(
            client, shutdown_requested=lambda: shutdown["requested"]
        )
        sink = ClosingSink()

        outcome = engine.analyze_case(make_request(), sink)

        assert isinstance(outcome, AnalysisFailure)
        assert outcome.error_code is AnalysisErrorCode.APP_INTERRUPTED
        assert outcome.error_stage is AnalysisStage.ATTRIBUTION
        assert len(client.requests) == 1
        assert [
            event.stage
            for event in sink.events
            if event.event_type == "STAGE_STARTED"
        ] == [AnalysisStage.PERCEPTION]

    def test_shutdown_marker_is_checked_again_before_first_stage(self) -> None:
        checks = {"count": 0}

        def shutdown_requested() -> bool:
            checks["count"] += 1
            return checks["count"] >= 2

        client = ScriptedGlmClient(happy_script())
        engine = make_engine(client, shutdown_requested=shutdown_requested)

        outcome = engine.analyze_case(make_request(), FakeEventSink())

        assert isinstance(outcome, AnalysisFailure)
        assert outcome.error_code is AnalysisErrorCode.APP_INTERRUPTED
        assert outcome.error_stage is AnalysisStage.PERCEPTION
        assert len(client.requests) == 0


class TestInputContractGuard:
    def test_non_case_input_rejected_without_model_calls(self) -> None:
        class Impostor:
            case_id = CASE_ID

        client = ScriptedGlmClient([])
        sink = FakeEventSink()

        outcome = make_engine(client).analyze_case(make_request(Impostor()), sink)

        assert isinstance(outcome, AnalysisFailure)
        assert outcome.error_code is AnalysisErrorCode.INPUT_CONTRACT_INVALID
        assert len(client.requests) == 0
        assert sink.events[-1].status == "FAILED"

    def test_prompt_version_mismatch_rejected(self) -> None:
        request = make_request()
        raw = request.model_dump()
        request_mismatch = AnalysisRequest(
            **{
                **raw,
                "case_input": loaded_case_input(),
                "perception_prompt_version": "v9",
            }
        )
        client = ScriptedGlmClient([])

        outcome = make_engine(client).analyze_case(request_mismatch, FakeEventSink())

        assert isinstance(outcome, AnalysisFailure)
        assert outcome.error_code is AnalysisErrorCode.INPUT_CONTRACT_INVALID
        assert len(client.requests) == 0

    def test_input_failure_event_sink_failure_is_not_hidden(self) -> None:
        request = make_request().model_copy(update={"perception_prompt_version": "v9"})
        client = ScriptedGlmClient([])

        outcome = make_engine(client).analyze_case(
            request, FakeEventSink(fail_on="ANALYSIS_COMPLETED")
        )

        assert isinstance(outcome, AnalysisFailure)
        assert outcome.error_code is AnalysisErrorCode.EVENT_SINK_FAILED
        assert outcome.error_stage is AnalysisStage.PERCEPTION

    @pytest.mark.parametrize(
        ("field", "stage"),
        [
            ("perception_contract_version", AnalysisStage.PERCEPTION),
            ("attribution_contract_version", AnalysisStage.ATTRIBUTION),
            ("strategy_contract_version", AnalysisStage.STRATEGY),
        ],
    )
    def test_result_contract_version_mismatch_rejected(
        self, field: str, stage: AnalysisStage
    ) -> None:
        request = make_request().model_copy(update={field: "v999"})
        client = ScriptedGlmClient([])

        outcome = make_engine(client).analyze_case(request, FakeEventSink())

        assert isinstance(outcome, AnalysisFailure)
        assert outcome.error_code is AnalysisErrorCode.INPUT_CONTRACT_INVALID
        assert outcome.error_stage is stage
        assert len(client.requests) == 0
