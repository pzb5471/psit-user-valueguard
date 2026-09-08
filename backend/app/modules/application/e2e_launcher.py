"""M4-09 真实 API 运行护套（仅测试/本地演示，不进生产路径）。

装配真实 M1 + 真实 AnalysisEngine + ScriptedGlmClient（确定性，零网络模型调用），
并在同一端口为已构建前端提供静态文件（规格第 14 节“单机同源”）。真实 GLM 由
M2-10 PoC 冻结后在生产 launcher 启用；本护套只供确定性验收与本地整机预览。
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"

# 复用 M1 ZIP 夹具与 M2 引擎样例（与 tests/e2e/backend/conftest.py 同一致约定）。
sys.path.insert(0, str(REPO_ROOT / "tests" / "contracts" / "data_ports"))
sys.path.insert(0, str(REPO_ROOT / "tests" / "m2" / "engine"))

import uvicorn  # noqa: E402
from engine_samples import (  # noqa: E402
    attribution_json,
    case_input_raw,
    perception_json,
    strategy_json,
)
from fastapi import Response  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from zip_fixtures import JPEG_BYTES, make_entries, make_zip, sha256_bytes  # noqa: E402

from app.modules.analysis.client import GlmResponse, ScriptedGlmClient  # noqa: E402
from app.modules.application.api.router import create_contract_app  # noqa: E402
from app.modules.application.config.settings import Settings  # noqa: E402
from app.modules.application.m2_wiring import build_analysis_engine  # noqa: E402
from app.modules.application.wiring import build_runtime, build_services  # noqa: E402

BATCH_ID = "batch-demo-0001"
CASE_ID = "case-0001"


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


def demo_zip_bytes() -> bytes:
    entries = make_entries(
        case_ids=(CASE_ID,),
        case_builder=lambda _case_id: _with_image(case_input_raw()),
        manifest_overrides={"batch_id": BATCH_ID, "evidence_count": 4},
    )
    return make_zip(entries)


def _perception_response() -> str:
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


def _resolve_image(_asset: str) -> tuple[str, bytes]:
    return "image/jpeg", JPEG_BYTES


def build_app():
    runtime = build_runtime(Path(tempfile.mkdtemp()) / "runtime_data")
    scripted = ScriptedGlmClient(
        [
            GlmResponse(content=_perception_response()),
            GlmResponse(content=attribution_json()),
            GlmResponse(content=strategy_json()),
        ]
    )
    engine = build_analysis_engine(scripted, image_data_resolver=_resolve_image)
    services = build_services(runtime, analysis_engine=engine)
    app = create_contract_app(
        settings=Settings.load(),
        services=services.application,
        run_service=services.run,
        review_service=services.review,
    )

    @app.get("/e2e/demo.zip")
    def get_demo_zip() -> Response:
        return Response(content=demo_zip_bytes(), media_type="application/zip")

    if FRONTEND_DIST.is_dir():
        # /api 与 /e2e 已先注册，静态兜底不遮蔽接口。
        app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")
    return app, services, runtime


def main() -> None:
    settings = Settings.load()
    app, services, runtime = build_app()
    try:
        uvicorn.run(app, host=settings.http.host, port=settings.http.port)
    finally:
        services.run.close()
        runtime.engine.dispose()


if __name__ == "__main__":
    main()
