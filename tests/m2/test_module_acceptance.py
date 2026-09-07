"""M2-09 模块验收：三阶段成功、证据不足与全部规定技术失败（规格第 9、15.1 节）。

用测试客户端跑通 M2 全部确定性路径并冻结事件与请求清单快照；全程零真实
GLM 调用（live_glm 属 M2-10 单独运行）。形成可供 M3 接线的稳定模块。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

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

_ENGINE_SAMPLES_DIR = Path(__file__).resolve().parent / "engine"
if str(_ENGINE_SAMPLES_DIR) not in sys.path:
    sys.path.insert(0, str(_ENGINE_SAMPLES_DIR))

from engine_samples import (  # noqa: E402
    CASE_ID,
    TRACE_ID,
    attribution_json,
    broken_perception_json,
    loaded_case_input,
    perception_json,
    strategy_json,
)

pytestmark = pytest.mark.task_m2_09

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

def _no_resolver(_asset_relative_path: str) -> tuple[str, bytes]:
    raise FileNotFoundError(_asset_relative_path)


class RecordingSink:
    def __init__(self) -> None:
        self.events: list[Any] = []

    def emit(self, event: Any) -> None:
        self.events.append(event)

    def types(self) -> list[str]:
        return [event.event_type for event in self.events]


def make_engine(client: ScriptedGlmClient) -> AnalysisEngine:
    return AnalysisEngine(
        model_client=client,
        image_data_resolver=_no_resolver,
        action_catalog=CATALOG,
    )


def make_request() -> AnalysisRequest:
    return AnalysisRequest(
        trace_id=TRACE_ID,
        case_run_id=1,
        case_input=loaded_case_input(),
        perception_contract_version="v1",
        attribution_contract_version="v1",
        strategy_contract_version="v1",
        perception_prompt_version="v1",
        attribution_prompt_version="v1",
        strategy_prompt_version="v1",
        action_catalog_version="v1",
    )


def insufficient_evidence_json() -> str:
    sample: dict[str, Any] = {
        "schema_version": "v1",
        "case_id": CASE_ID,
        "risk_summary": "现有证据不足以可靠判断风险原因。",
        "primary_cause": {
            "category": "INSUFFICIENT_EVIDENCE",
            "explanation": "缺少质检与物流记录，无法在候选原因间做出判断。",
            "evidence_ids": [],
        },
    }
    return json.dumps(sample, ensure_ascii=False)


def run(script: list[Any], sink: RecordingSink | None = None) -> tuple[Any, RecordingSink]:
    sink = sink or RecordingSink()
    outcome = make_engine(ScriptedGlmClient(script)).analyze_case(make_request(), sink)
    return outcome, sink


class TestThreeStageSuccess:
    """三阶段成功：事件序列快照与正常路径三次请求。"""

    def test_success_event_snapshot(self) -> None:
        outcome, sink = run(
            [
                GlmResponse(content=perception_json()),
                GlmResponse(content=attribution_json()),
                GlmResponse(content=strategy_json()),
            ]
        )

        assert isinstance(outcome, AnalysisSuccess)
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

    def test_success_carries_three_contract_results(self) -> None:
        outcome, _ = run(
            [
                GlmResponse(content=perception_json()),
                GlmResponse(content=attribution_json()),
                GlmResponse(content=strategy_json()),
            ]
        )

        assert isinstance(outcome, AnalysisSuccess)
        assert outcome.attribution.risk_summary
        assert outcome.decision.actions[0].action_type.value == "EVIDENCE_CHECK"


class TestInsufficientEvidence:
    """证据不足是合格业务结果：结构完整即成功，不属于技术失败。"""

    def test_insufficient_evidence_is_success(self) -> None:
        outcome, sink = run(
            [
                GlmResponse(content=perception_json()),
                GlmResponse(content=insufficient_evidence_json()),
                GlmResponse(content=strategy_json()),
            ]
        )

        assert isinstance(outcome, AnalysisSuccess)
        assert outcome.attribution.primary_cause.category.value == "INSUFFICIENT_EVIDENCE"
        assert "ANALYSIS_COMPLETED" in sink.types()
        assert "STAGE_FAILED" not in sink.types()


class TestAllDefinedTechnicalFailures:
    """全部规定技术失败：每阶段请求上限、不可重试、修复链路与事件出口。"""

    def test_timeout_exhausted(self) -> None:
        outcome, _ = run(
            [
                GlmClientError(AnalysisErrorCode.MODEL_TIMEOUT, "t1"),
                GlmClientError(AnalysisErrorCode.MODEL_TIMEOUT, "t2"),
                GlmClientError(AnalysisErrorCode.MODEL_TIMEOUT, "t3"),
            ]
        )

        assert outcome.error_code is AnalysisErrorCode.MODEL_TIMEOUT
        assert outcome.error_stage is AnalysisStage.PERCEPTION
        assert outcome.attempts_exhausted is True

    def test_network_exhausted(self) -> None:
        outcome, _ = run(
            [
                GlmClientError(AnalysisErrorCode.MODEL_NETWORK, "n1"),
                GlmClientError(AnalysisErrorCode.MODEL_NETWORK, "n2"),
                GlmClientError(AnalysisErrorCode.MODEL_NETWORK, "n3"),
            ]
        )

        assert outcome.error_code is AnalysisErrorCode.MODEL_NETWORK
        assert outcome.attempts_exhausted is True

    def test_rate_limited_exhausted(self) -> None:
        outcome, _ = run(
            [
                GlmClientError(AnalysisErrorCode.MODEL_RATE_LIMITED, "r1"),
                GlmClientError(AnalysisErrorCode.MODEL_RATE_LIMITED, "r2"),
                GlmClientError(AnalysisErrorCode.MODEL_RATE_LIMITED, "r3"),
            ]
        )

        assert outcome.error_code is AnalysisErrorCode.MODEL_RATE_LIMITED
        assert outcome.attempts_exhausted is True

    def test_provider_error_exhausted(self) -> None:
        outcome, _ = run(
            [
                GlmClientError(AnalysisErrorCode.MODEL_PROVIDER_ERROR, "p1"),
                GlmClientError(AnalysisErrorCode.MODEL_PROVIDER_ERROR, "p2"),
                GlmClientError(AnalysisErrorCode.MODEL_PROVIDER_ERROR, "p3"),
            ]
        )

        assert outcome.error_code is AnalysisErrorCode.MODEL_PROVIDER_ERROR
        assert outcome.attempts_exhausted is True

    def test_auth_rejected_not_retryable(self) -> None:
        outcome, _ = run([GlmClientError(AnalysisErrorCode.MODEL_AUTH_REJECTED, "401")])

        assert outcome.error_code is AnalysisErrorCode.MODEL_AUTH_REJECTED
        assert outcome.attempts_exhausted is False

    def test_request_invalid_not_retryable(self) -> None:
        outcome, _ = run([GlmClientError(AnalysisErrorCode.MODEL_REQUEST_INVALID, "400")])

        assert outcome.error_code is AnalysisErrorCode.MODEL_REQUEST_INVALID
        assert outcome.attempts_exhausted is False

    def test_output_invalid_after_one_repair(self) -> None:
        outcome, _ = run(
            [
                GlmResponse(content=broken_perception_json()),
                GlmResponse(content=broken_perception_json()),
            ]
        )

        assert outcome.error_code is AnalysisErrorCode.MODEL_OUTPUT_INVALID
        assert outcome.error_stage is AnalysisStage.PERCEPTION
        assert outcome.attempts_exhausted is True

    def test_repair_network_failure_not_retried(self) -> None:
        outcome, _ = run(
            [
                GlmResponse(content=broken_perception_json()),
                GlmClientError(AnalysisErrorCode.MODEL_TIMEOUT, "修复超时"),
            ]
        )

        assert outcome.error_code is AnalysisErrorCode.MODEL_TIMEOUT
        assert outcome.attempts_exhausted is True

    def test_event_sink_failure_stops_case(self) -> None:
        client = ScriptedGlmClient([GlmResponse(content=perception_json())])

        class BrokenSink(RecordingSink):
            def emit(self, event: Any) -> None:
                if event.event_type == "STAGE_RESULT_VALIDATED":
                    raise RuntimeError("落库失败（模拟）")
                self.events.append(event)

        sink = BrokenSink()
        outcome = make_engine(client).analyze_case(make_request(), sink)

        assert isinstance(outcome, AnalysisFailure)
        assert outcome.error_code is AnalysisErrorCode.EVENT_SINK_FAILED
        assert outcome.attempts_exhausted is False
        assert len(client.requests) == 1

    def test_input_contract_invalid_on_impostor_case_input(self) -> None:
        class Impostor:
            case_id = CASE_ID

        client = ScriptedGlmClient([])
        sink = RecordingSink()
        request = AnalysisRequest(
            trace_id=TRACE_ID,
            case_run_id=1,
            case_input=Impostor(),
            perception_contract_version="v1",
            attribution_contract_version="v1",
            strategy_contract_version="v1",
            perception_prompt_version="v1",
            attribution_prompt_version="v1",
            strategy_prompt_version="v1",
            action_catalog_version="v1",
        )

        outcome = make_engine(client).analyze_case(request, sink)

        assert isinstance(outcome, AnalysisFailure)
        assert outcome.error_code is AnalysisErrorCode.INPUT_CONTRACT_INVALID
        assert len(client.requests) == 0


class TestSnapshots:
    """请求清单与失败事件序列快照（确定性路径）。"""

    def test_request_manifest_snapshot(self) -> None:
        _, sink = run(
            [
                GlmResponse(content=perception_json()),
                GlmResponse(content=attribution_json()),
                GlmResponse(content=strategy_json()),
            ]
        )

        manifests = [
            event.request_manifest
            for event in sink.events
            if event.event_type == "MODEL_ATTEMPT_FINISHED"
        ]
        assert [m["stage"] for m in manifests] == [
            "PERCEPTION",
            "ATTRIBUTION",
            "STRATEGY",
        ]
        for manifest in manifests:
            assert manifest["manifest_version"] == "v1"
            assert manifest["model"] == "glm-5.3-flash"
            assert "system_prompt_sha256" in manifest
            assert "user_content_sha256" in manifest

    def test_failure_event_snapshot(self) -> None:
        _, sink = run([GlmClientError(AnalysisErrorCode.MODEL_AUTH_REJECTED, "401")])

        assert [
            (event.event_type, str(getattr(event, "stage", "")))
            for event in sink.events
        ] == [
            ("STAGE_STARTED", "PERCEPTION"),
            ("MODEL_ATTEMPT_FINISHED", "PERCEPTION"),
            ("STAGE_FAILED", "PERCEPTION"),
            ("ANALYSIS_COMPLETED", ""),
        ]

    def test_success_event_snapshot_types(self) -> None:
        _, sink = run(
            [
                GlmResponse(content=perception_json()),
                GlmResponse(content=attribution_json()),
                GlmResponse(content=strategy_json()),
            ]
        )

        assert sink.types().count("STAGE_STARTED") == 3
        assert sink.types().count("MODEL_ATTEMPT_FINISHED") == 3
        assert sink.types().count("STAGE_RESULT_VALIDATED") == 3
        assert sink.types().count("ANALYSIS_COMPLETED") == 1
        assert sink.types().count("STAGE_FAILED") == 0
