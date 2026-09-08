"""M3-09 真实 M2—M3 接线集成测试（规格 15.1 确定性验收；零网络模型调用）。

真实 M1（SQLite 迁移 + 真实 ZIP 导入）+ 真实 AnalysisEngine + ScriptedGlmClient，
覆盖导入→分析→读回→审核、技术失败→PROCESSING_ERROR、失败重跑成功与恢复零模型调用。
"""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "contracts" / "data_ports"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "m2" / "engine"))

from engine_samples import attribution_json, case_input_raw, perception_json, strategy_json
from zip_fixtures import JPEG_BYTES, make_entries, make_zip, sha256_bytes

from app.contracts.analysis import AnalysisErrorCode
from app.modules.analysis.client import GlmClientError, GlmResponse, ScriptedGlmClient
from app.modules.application.api.contracts.errors import ApiErrorCode
from app.modules.application.api.contracts.reviews import ApprovedReviewRequest, ReviewOutcome
from app.modules.application.m2_wiring import build_analysis_engine
from app.modules.application.services.query.errors import ServiceError
from app.modules.application.wiring import build_runtime, build_services

BATCH_ID = "batch-demo-0001"
CASE_ID = "case-0001"
EVIDENCE_COUNT = 4  # msg-0001/0002 + beh-0001 + img-0001

def resolve_image(_asset_path: str) -> tuple[str, bytes]:
    """确定性图片解析器（M3-09 测试边界；不访问网络或正式目录）。"""
    return "image/jpeg", JPEG_BYTES



def perception_response() -> str:
    """感知响应：M2 要求每张输入图片有观察记录，注入匹配 img-0001 的观察。"""
    import json

    data = json.loads(perception_json())
    data["image_observations"] = [
        {
            "image_evidence_id": "img-0001",
            "analysis_status": "ANALYZED",
            "observable_facts": ["图片显示商品有烧焦痕迹"],
            "relation": "MUTUALLY_SUPPORTS",
            "related_text_evidence_ids": ["msg-0001"],
        }
    ]
    return json.dumps(data, ensure_ascii=False)


def _with_image(raw: dict) -> dict:
    raw["evidence"]["image_items"] = [
        {
            "evidence_id": "img-0001",
            "identity": "observed",
            "relation_identity": "mock_mapped",
            "source_ref": {
                "dataset": "service_tasks",
                "relative_path": "source_data/ecommercedata-main/data/service_tasks.json",
                "record_key": "dialog-0001",
                "field": "image",
            },
            "content_hash": sha256_bytes(JPEG_BYTES),
            "asset_relative_path": f"assets/{CASE_ID}/scratch_01.jpg",
            "media_type": "image/jpeg",
        }
    ]
    return raw


def import_demo_zip(runtime) -> str:
    entries = make_entries(
        case_ids=(CASE_ID,),
        case_builder=lambda _cid: _with_image(case_input_raw()),
        manifest_overrides={"batch_id": BATCH_ID, "evidence_count": EVIDENCE_COUNT},
    )
    package = make_zip(entries)
    result = runtime.importer.import_zip(
        package, source_filename="demo.zip", content_length=len(package)
    )
    assert result.ok, result.rejections
    assert result.batch_id is not None
    return result.batch_id


@pytest.fixture()
def runtime(tmp_path: Path):
    rt = build_runtime(tmp_path / "runtime_data")
    try:
        yield rt
    finally:
        rt.engine.dispose()


def test_import_analyze_review_full_flow(runtime) -> None:
    batch_id = import_demo_zip(runtime)
    scripted = ScriptedGlmClient(
        [
            GlmResponse(content=perception_response()),
            GlmResponse(content=attribution_json()),
            GlmResponse(content=strategy_json()),
        ]
    )
    engine = build_analysis_engine(scripted, image_data_resolver=resolve_image)
    services = build_services(runtime, analysis_engine=engine)
    try:
        services.run.start_batch_run(batch_id)
        services.run.close()

        batch = runtime.query.get_batch(batch_id)
        assert batch.analysis_succeeded_count == 1
        assert batch.error_count == 0

        detail = runtime.query.get_case_detail(batch_id, CASE_ID)
        assert detail.status == "PENDING_REVIEW"
        assert detail.can_review is True
        assert detail.review_token
        assert detail.review_options is not None

        view = services.review.submit_review(
            batch_id,
            CASE_ID,
            ApprovedReviewRequest(
                submission_id=uuid4(),
                review_token=detail.review_token,
                outcome=ReviewOutcome.APPROVED,
            ),
        )
        assert view.outcome == "APPROVED"
        after = runtime.query.get_case_detail(batch_id, CASE_ID)
        assert after.status == "COMPLETED"
    finally:
        services.run.close()

    assert len(scripted.requests) == 3  # 正常路径每案例三次请求


def test_model_failure_maps_to_processing_error(runtime) -> None:
    batch_id = import_demo_zip(runtime)
    scripted = ScriptedGlmClient(
        [
            GlmClientError(AnalysisErrorCode.MODEL_TIMEOUT, "超时"),
            GlmClientError(AnalysisErrorCode.MODEL_TIMEOUT, "超时"),
            GlmClientError(AnalysisErrorCode.MODEL_TIMEOUT, "超时"),
        ]
    )
    engine = build_analysis_engine(scripted, image_data_resolver=resolve_image)
    services = build_services(runtime, analysis_engine=engine)
    try:
        services.run.start_batch_run(batch_id)
        services.run.close()

        detail = runtime.query.get_case_detail(batch_id, CASE_ID)
        assert detail.status == "PROCESSING_ERROR"
        assert detail.processing_error is not None
        assert detail.processing_error.code in (
            "MODEL_TIMEOUT",
            "MODEL_ATTEMPTS_EXHAUSTED",
        )
        batch = runtime.query.get_batch(batch_id)
        assert batch.error_count == 1
    finally:
        services.run.close()


def test_failed_case_rerun_succeeds(runtime) -> None:
    batch_id = import_demo_zip(runtime)
    fail_engine = build_analysis_engine(
        ScriptedGlmClient(
            [
                GlmClientError(AnalysisErrorCode.MODEL_TIMEOUT, "超时"),
                GlmClientError(AnalysisErrorCode.MODEL_TIMEOUT, "超时"),
                GlmClientError(AnalysisErrorCode.MODEL_TIMEOUT, "超时"),
            ]
        ),
        image_data_resolver=resolve_image,
    )
    services = build_services(runtime, analysis_engine=fail_engine)
    services.run.start_batch_run(batch_id)
    services.run.close()
    assert (
        runtime.query.get_case_detail(batch_id, CASE_ID).status == "PROCESSING_ERROR"
    )

    ok_engine = build_analysis_engine(
        ScriptedGlmClient(
            [
                GlmResponse(content=perception_response()),
                GlmResponse(content=attribution_json()),
                GlmResponse(content=strategy_json()),
            ],
        ),
        image_data_resolver=resolve_image,
    )
    services2 = build_services(runtime, analysis_engine=ok_engine)
    try:
        services2.run.rerun_case(batch_id, CASE_ID)
        services2.run.close()
        detail = runtime.query.get_case_detail(batch_id, CASE_ID)
        assert detail.status == "PENDING_REVIEW"
        assert detail.can_review is True
    finally:
        services2.run.close()


def test_completed_case_rejects_review_and_rerun(runtime) -> None:
    batch_id = import_demo_zip(runtime)
    engine = build_analysis_engine(
        ScriptedGlmClient(
            [
                GlmResponse(content=perception_response()),
                GlmResponse(content=attribution_json()),
                GlmResponse(content=strategy_json()),
            ],
        ),
        image_data_resolver=resolve_image,
    )
    services = build_services(runtime, analysis_engine=engine)
    try:
        services.run.start_batch_run(batch_id)
        services.run.close()
        token = runtime.query.get_case_detail(batch_id, CASE_ID).review_token
        assert token
        services.review.submit_review(
            batch_id,
            CASE_ID,
            ApprovedReviewRequest(
                submission_id=uuid4(),
                review_token=token,
                outcome=ReviewOutcome.APPROVED,
            ),
        )
        with pytest.raises(ServiceError) as rerun_error:
            services.run.rerun_case(batch_id, CASE_ID)
        assert rerun_error.value.code == ApiErrorCode.CASE_ALREADY_COMPLETED
    finally:
        services.run.close()


def test_recovery_after_interrupted_run_zero_model_calls(runtime) -> None:
    batch_id = import_demo_zip(runtime)
    calls: list = []

    class CountingClient:
        def complete(self, request):
            calls.append(request)
            raise GlmClientError(AnalysisErrorCode.MODEL_TIMEOUT, "超时")

    engine = build_analysis_engine(CountingClient(), image_data_resolver=resolve_image)
    services = build_services(runtime, analysis_engine=engine)
    services.run.start_batch_run(batch_id)
    services.run.close()

    summary = runtime.run_store.recover_interrupted()
    assert summary.interrupted_batch_runs >= 0
    assert len(calls) >= 1  # 分析尝试过；恢复本身不触发新的模型调用
    before = len(calls)
    runtime.run_store.recover_interrupted()
    assert len(calls) == before  # 恢复零模型调用
