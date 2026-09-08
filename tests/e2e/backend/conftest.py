"""M3-09 后端 E2E 夹具：真实 M1 + 真实 AnalysisEngine + Scripted 客户端，走 HTTP。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "contracts" / "data_ports"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "m2" / "engine"))

import pytest
from engine_samples import attribution_json, case_input_raw, perception_json, strategy_json
from zip_fixtures import JPEG_BYTES, make_entries, make_zip, sha256_bytes

from app.modules.analysis.client import GlmResponse, ScriptedGlmClient
from app.modules.application.m2_wiring import build_analysis_engine
from app.modules.application.wiring import build_runtime, build_services

BATCH_ID = "batch-demo-0001"
CASE_ID = "case-0001"
_JPEG = JPEG_BYTES
_PNG_HASH = sha256_bytes(JPEG_BYTES)


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
            "content_hash": _PNG_HASH,
            "asset_relative_path": f"assets/{CASE_ID}/scratch_01.jpg",
            "media_type": "image/jpeg",
        }
    ]
    return raw


def _resolve_image(_asset: str) -> tuple[str, bytes]:
    return "image/jpeg", _JPEG


def make_zip_bytes() -> bytes:
    entries = make_entries(
        case_ids=(CASE_ID,),
        case_builder=lambda _c: _with_image(case_input_raw()),
        manifest_overrides={"batch_id": BATCH_ID, "evidence_count": 4},
    )
    return make_zip(entries)


def perception_response() -> str:
    """感知响应：为案例的 img-0001 图片注入观察记录（M2 每张输入图片须有观察）。"""
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


@pytest.fixture()
def zip_bytes() -> bytes:
    return make_zip_bytes()


@pytest.fixture()
def e2e_app():
    """真实 M3 服务 + 真实引擎 + Scripted 客户端的 HTTP 应用。

    返回 (TestClient, scripted, runtime)；脚本需按测试场景补足。
    """
    import tempfile

    from fastapi.testclient import TestClient

    from app.modules.application.api.router import create_contract_app

    rt = build_runtime(Path(tempfile.mkdtemp()) / "runtime_data")
    scripted = ScriptedGlmClient(
        [
            GlmResponse(content=perception_response()),
            GlmResponse(content=attribution_json()),
            GlmResponse(content=strategy_json()),
        ]
    )
    engine = build_analysis_engine(scripted, image_data_resolver=_resolve_image)
    services = build_services(rt, analysis_engine=engine)
    app = create_contract_app(
        services=services.application,
        run_service=services.run,
        review_service=services.review,
    )
    try:
        yield TestClient(app), scripted, rt
    finally:
        services.run.close()
        rt.engine.dispose()
