"""M2-10：固定 15 案例真实 GLM PoC，独立于普通确定性门禁。"""

from __future__ import annotations

import json
import os
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any

import pytest

from app.contracts.analysis import (
    AnalysisEvent,
    AnalysisFailure,
    AnalysisRequest,
    AnalysisSuccess,
)
from app.contracts.data import CaseInput
from app.modules.analysis.client import GlmCallParams, GlmClient
from app.modules.application.config.settings import Settings
from app.modules.application.m2_wiring import build_analysis_engine
from app.modules.application.wiring import build_versions
from app.modules.data.importing.zip_stage import ZipImportStage

pytestmark = pytest.mark.live_glm

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = REPO_ROOT / "runtime_data" / "mock_dataset_v1"
PACKAGE_SPECS = (
    (DATA_ROOT / "demo_batch_v1.zip", 10),
    (DATA_ROOT / "acceptance_batch_v1.zip", 5),
)


class RecordingSink:
    def __init__(self) -> None:
        self.events: list[AnalysisEvent] = []
        self._lock = Lock()

    def emit(self, event: AnalysisEvent) -> None:
        with self._lock:
            self.events.append(event)


def _load_cases(tmp_path: Path) -> tuple[list[CaseInput], dict[str, dict[str, bytes]]]:
    cases: list[CaseInput] = []
    package_entries: dict[str, dict[str, bytes]] = {}
    for package_path, expected_count in PACKAGE_SPECS:
        raw = package_path.read_bytes()
        staged = ZipImportStage(tmp_root=tmp_path).stage(raw)
        assert staged.ok, "; ".join(item.message for item in staged.rejections)
        assert staged.case_count == expected_count
        with zipfile.ZipFile(package_path) as archive:
            entries = {name: archive.read(name) for name in archive.namelist()}
            manifest = json.loads(entries["manifest.json"])
            loaded = [
                CaseInput.model_validate_json(entries[name])
                for name in manifest["case_files"]
            ]
        package_entries[manifest["batch_id"]] = entries
        cases.extend(loaded)
    assert len(cases) == 15
    return cases, package_entries


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _report_markdown(summary: dict[str, Any]) -> str:
    return "\n".join(
        (
            "# GLM-5.3-Flash 固定案例 PoC",
            "",
            f"- run_id: `{summary['run_id']}`",
            f"- 自动结构门：`{summary['automated_gate']}`",
            f"- 案例：{summary['successful_cases']}/{summary['case_count']}",
            f"- 严格通过阶段：{summary['validated_stages']}/45",
            f"- 模型尝试：{summary['model_attempts']}",
            f"- 总耗时：{summary['duration_seconds']} 秒",
            f"- Prompt Token：{summary['prompt_tokens']}",
            f"- Completion Token：{summary['completion_tokens']}",
            "- 演讲版项目负责人验收：PROJECT_OWNER_ACCEPTED（ADR 0087）",
            "- 生产门禁：自动结构门通过后按受审查配置启用",
            "",
        )
    )


def test_fixed_15_case_live_glm_poc(tmp_path: Path) -> None:
    missing = []
    if not os.environ.get("ZAI_API_KEY", "").strip():
        missing.append("ZAI_API_KEY")
    missing.extend(str(path) for path, _ in PACKAGE_SPECS if not path.is_file())
    if missing:
        pytest.fail(
            "LIVE_GLM_PREREQUISITE_MISSING: "
            + ", ".join(missing)
            + "; run scripts/prepare-demo-data.ps1 and provide the key via environment only"
        )

    effort = os.environ.get("PSIT_POC_REASONING_EFFORT", "high")
    if effort not in {"high", "max"}:
        pytest.fail("PSIT_POC_REASONING_EFFORT 只允许 high 或 max")
    settings = Settings.load()
    concurrency = int(
        os.environ.get("PSIT_POC_CONCURRENCY", settings.executor.case_concurrency)
    )
    if concurrency not in {1, 2, 3}:
        pytest.fail("PSIT_POC_CONCURRENCY 只允许 1、2 或 3")

    cases, entries_by_batch = _load_cases(tmp_path)

    def resolve_image(case: CaseInput, path: str) -> tuple[str, bytes]:
        image = next(
            item
            for item in case.evidence.image_items
            if item.asset_relative_path == path
        )
        return image.media_type.value, entries_by_batch[case.batch_id][path]

    params = GlmCallParams(
        max_tokens=settings.analysis.max_tokens,
        reasoning_effort=effort,
    )
    client = GlmClient(
        api_key=os.environ["ZAI_API_KEY"],
        connect_timeout_seconds=settings.analysis.connect_timeout_seconds,
        response_timeout_seconds=settings.analysis.response_timeout_seconds,
        params=params,
    )
    engine = build_analysis_engine(
        client,
        case_image_data_resolver=resolve_image,
        connect_timeout_seconds=settings.analysis.connect_timeout_seconds,
        response_timeout_seconds=settings.analysis.response_timeout_seconds,
        params=params,
    )
    versions = build_versions()
    started = time.monotonic()
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    artifact_dir = REPO_ROOT / "artifacts" / "poc" / run_id

    def run_case(indexed: tuple[int, CaseInput]) -> dict[str, Any]:
        index, case = indexed
        sink = RecordingSink()
        case_started = time.monotonic()
        request = AnalysisRequest(
            trace_id=f"poc-{run_id}-{case.case_id}",
            case_run_id=index,
            case_input=case,
            perception_contract_version=versions.perception_contract_version,
            attribution_contract_version=versions.attribution_contract_version,
            strategy_contract_version=versions.strategy_contract_version,
            perception_prompt_version=versions.perception_prompt_version,
            attribution_prompt_version=versions.attribution_prompt_version,
            strategy_prompt_version=versions.strategy_prompt_version,
            action_catalog_version=versions.action_catalog_version,
        )
        try:
            outcome = engine.analyze_case(request, sink)
            outcome_payload = outcome.model_dump(mode="json")
        except Exception as error:
            outcome = None
            outcome_payload = {
                "status": "FAILED",
                "error_type": error.__class__.__name__,
                "error": str(error)[:512],
            }
        events = [event.model_dump(mode="json") for event in sink.events]
        return {
            "case_id": case.case_id,
            "batch_id": case.batch_id,
            "duration_seconds": round(time.monotonic() - case_started, 3),
            "outcome": outcome_payload,
            "events": events,
            "validated_stages": sum(
                event["event_type"] == "STAGE_RESULT_VALIDATED" for event in events
            ),
            "model_attempts": sum(
                event["event_type"] == "MODEL_ATTEMPT_FINISHED" for event in events
            ),
            "success": isinstance(outcome, AnalysisSuccess),
            "failure": isinstance(outcome, AnalysisFailure),
        }

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        results = list(executor.map(run_case, enumerate(cases, start=1)))
    results.sort(key=lambda item: (item["batch_id"], item["case_id"]))
    duration = round(time.monotonic() - started, 3)

    attempt_events = [
        event
        for result in results
        for event in result["events"]
        if event["event_type"] == "MODEL_ATTEMPT_FINISHED"
    ]
    summary = {
        "run_id": run_id,
        "model": params.model_name,
        "reasoning_effort": effort,
        "concurrency": concurrency,
        "case_count": len(results),
        "successful_cases": sum(result["success"] for result in results),
        "failed_cases": sum(not result["success"] for result in results),
        "validated_stages": sum(result["validated_stages"] for result in results),
        "model_attempts": len(attempt_events),
        "prompt_tokens": sum(event.get("prompt_tokens") or 0 for event in attempt_events),
        "completion_tokens": sum(
            event.get("completion_tokens") or 0 for event in attempt_events
        ),
        "duration_seconds": duration,
        "automated_gate": (
            "PASSED"
            if len(results) == 15
            and all(result["success"] for result in results)
            and sum(result["validated_stages"] for result in results) == 45
            else "FAILED"
        ),
        "demo_acceptance": "PROJECT_OWNER_ACCEPTED",
    }
    _write_json(artifact_dir / "summary.json", summary)
    _write_json(artifact_dir / "case-results.json", results)
    report_path = REPO_ROOT / "docs" / "poc" / "glm-5.3-flash-poc.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(_report_markdown(summary), encoding="utf-8")

    assert summary["successful_cases"] == 15, artifact_dir
    assert summary["validated_stages"] == 45, artifact_dir
    assert summary["automated_gate"] == "PASSED", artifact_dir
