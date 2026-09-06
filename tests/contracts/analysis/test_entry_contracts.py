"""M2-01 合同验收：分析入口请求与成功/失败结果联合（规格第 9.1 节）。

AnalysisRequest 只组合 trace_id、内部 case_run_id、CaseInput v1、三份结果合同
版本、三阶段 Prompt 版本与动作目录版本；AnalysisOutcome 是严格的成功或失败联合。
CaseInput v1 的完整合同由 M1-01 冻结，本卡通过协议声明最小结构面。
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from analysis_samples import attribution_result, decision_package, perception_result
from pydantic import TypeAdapter, ValidationError

from app.contracts.analysis import (
    AnalysisErrorCode,
    AnalysisOutcome,
    AnalysisRequest,
    AnalysisStage,
    AnalysisSuccess,
)

pytestmark = pytest.mark.task_m2_01

OUTCOME_ADAPTER = TypeAdapter(AnalysisOutcome)


class FakeCaseInput:
    """真实 CaseInput v1 的结构替身：至少携带协议要求的 case_id。"""

    case_id: str = "case-0001"


class NotACaseInput:
    """缺少 case_id 结构面的对象，必须被拒绝。"""

    batch_id: str = "batch-0001"


def outcome_success(**overrides: Any) -> dict[str, Any]:
    sample: dict[str, Any] = {
        "status": "SUCCESS",
        "perception": perception_result(),
        "attribution": attribution_result(),
        "decision": decision_package(),
    }
    sample.update(overrides)
    return sample


def outcome_failure(**overrides: Any) -> dict[str, Any]:
    sample: dict[str, Any] = {
        "status": "FAILED",
        "error_code": "MODEL_TIMEOUT",
        "error_stage": "PERCEPTION",
        "attempts_exhausted": True,
        "trace_id": "trace-0001",
    }
    sample.update(overrides)
    return sample


def entry_request(**overrides: Any) -> dict[str, Any]:
    sample: dict[str, Any] = {
        "trace_id": "trace-0001",
        "case_run_id": 7,
        "case_input": FakeCaseInput(),
        "perception_contract_version": "v1",
        "attribution_contract_version": "v1",
        "strategy_contract_version": "v1",
        "perception_prompt_version": "v1",
        "attribution_prompt_version": "v1",
        "strategy_prompt_version": "v1",
        "action_catalog_version": "v1",
    }
    sample.update(overrides)
    return sample


def parse_outcome(sample: dict[str, Any]) -> Any:
    return OUTCOME_ADAPTER.validate_json(json.dumps(sample, ensure_ascii=False))


class TestAnalysisRequest:
    def test_accepts_protocol_shaped_case_input(self) -> None:
        request = AnalysisRequest(**entry_request())
        assert request.case_run_id == 7
        assert request.case_input.case_id == "case-0001"

    def test_rejects_case_input_without_case_id_surface(self) -> None:
        with pytest.raises(ValidationError):
            AnalysisRequest(**entry_request(case_input=NotACaseInput()))

    def test_requires_all_version_fields(self) -> None:
        sample = entry_request()
        del sample["action_catalog_version"]
        with pytest.raises(ValidationError):
            AnalysisRequest(**sample)

    def test_rejects_extra_field(self) -> None:
        with pytest.raises(ValidationError):
            AnalysisRequest(**entry_request(sealed_answer="hidden"))

    def test_rejects_non_positive_case_run_id(self) -> None:
        with pytest.raises(ValidationError):
            AnalysisRequest(**entry_request(case_run_id=0))

    def test_rejects_blank_trace_id(self) -> None:
        with pytest.raises(ValidationError):
            AnalysisRequest(**entry_request(trace_id="  "))

    def test_rejects_string_case_run_id_in_strict_mode(self) -> None:
        with pytest.raises(ValidationError):
            AnalysisRequest(**entry_request(case_run_id="7"))


class TestAnalysisOutcome:
    def test_success_carries_three_results(self) -> None:
        outcome = parse_outcome(outcome_success())
        assert isinstance(outcome, AnalysisSuccess)
        assert outcome.perception.case_id == "case-0001"

    def test_success_requires_same_case_id_across_results(self) -> None:
        sample = outcome_success()
        sample["decision"]["case_id"] = "case-0002"
        with pytest.raises(ValidationError):
            parse_outcome(sample)

    def test_success_rejects_extra_field(self) -> None:
        with pytest.raises(ValidationError):
            parse_outcome(outcome_success(confidence=0.9))

    def test_failure_carries_stable_error_fields(self) -> None:
        outcome = parse_outcome(outcome_failure())
        assert outcome.error_code == AnalysisErrorCode.MODEL_TIMEOUT
        assert outcome.error_stage == AnalysisStage.PERCEPTION
        assert outcome.attempts_exhausted is True

    def test_failure_requires_attempts_exhausted_flag(self) -> None:
        sample = outcome_failure()
        del sample["attempts_exhausted"]
        with pytest.raises(ValidationError):
            parse_outcome(sample)

    def test_rejects_unknown_status(self) -> None:
        with pytest.raises(ValidationError):
            parse_outcome(outcome_failure(status="PENDING"))

    def test_rejects_unknown_error_code(self) -> None:
        with pytest.raises(ValidationError):
            parse_outcome(outcome_failure(error_code="SOMETHING_LOOSE"))

    def test_error_codes_map_spec_retry_categories(self) -> None:
        assert {member.value for member in AnalysisErrorCode} == {
            "MODEL_TIMEOUT",
            "MODEL_NETWORK",
            "MODEL_RATE_LIMITED",
            "MODEL_PROVIDER_ERROR",
            "MODEL_AUTH_REJECTED",
            "MODEL_REQUEST_INVALID",
            "MODEL_OUTPUT_INVALID",
            "INPUT_CONTRACT_INVALID",
            "EVENT_SINK_FAILED",
            "APP_INTERRUPTED",
        }

    def test_error_stage_covers_three_stages_only(self) -> None:
        assert {member.value for member in AnalysisStage} == {
            "PERCEPTION",
            "ATTRIBUTION",
            "STRATEGY",
        }
