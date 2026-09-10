"""M3-08 本机启动入口；真实 GLM 由 M2-10 验收后接入。"""

from __future__ import annotations

import uvicorn

from app.modules.application.api.router import create_contract_app
from app.modules.application.config.settings import Settings, find_project_root
from app.modules.application.static_frontend import mount_frontend
from app.modules.application.wiring import build_runtime, build_services, instance_lock


class _AnalysisUnavailable:
    def health_check(self) -> bool:
        return False

    def analyze_case(self, request, event_sink):
        raise RuntimeError("真实 GLM 尚未接入；请完成 M2-10 验收")


def main() -> None:
    settings = Settings.load()
    unavailable_message = (
        "未配置 ZAI_API_KEY，分析不可用；历史结果仍可查看"
        if settings.zai_api_key is None
        else "真实 GLM 验收尚未完成，分析功能暂不可用"
    )
    runtime = build_runtime(settings.resolve_runtime_dir())
    lock = instance_lock(runtime.runtime_dir)
    lock.__enter__()
    services = None
    analysis_engine = _AnalysisUnavailable()
    try:
        services = build_services(
            runtime,
            analysis_engine=analysis_engine,
            max_concurrency=settings.executor.case_concurrency,
            analysis_available=False,
            analysis_unavailable_message=unavailable_message,
        )
        app = create_contract_app(
            settings=settings,
            services=services.application,
            run_service=services.run,
            review_service=services.review,
        )
        if settings.zai_api_key is not None:
            # 已配置密钥也不等于真实 GLM 已完成 M2-10 验收。
            app.state.analysis_health = analysis_engine
        mount_frontend(app, find_project_root() / "frontend" / "dist")
        runtime.run_store.recover_interrupted()
        uvicorn.run(app, host=settings.http.host, port=settings.http.port)
    finally:
        if services is not None:
            services.run.close()
        runtime.engine.dispose()
        lock.__exit__(None, None, None)


if __name__ == "__main__":
    main()
