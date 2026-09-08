"""M3-08 本机启动入口；M2 真实引擎由 M3-09 替换。"""

from __future__ import annotations

import uvicorn

from app.modules.application.api.router import create_contract_app
from app.modules.application.config.settings import Settings
from app.modules.application.wiring import build_runtime, build_services, instance_lock


class _AnalysisUnavailable:
    def analyze_case(self, request, event_sink):
        raise RuntimeError("分析引擎尚未接入；请完成 M3-09")


def main() -> None:
    settings = Settings.load()
    runtime = build_runtime(settings.resolve_runtime_dir())
    lock = instance_lock(runtime.runtime_dir)
    lock.__enter__()
    services = None
    try:
        services = build_services(
            runtime,
            analysis_engine=_AnalysisUnavailable(),
            max_concurrency=settings.executor.case_concurrency,
        )
        app = create_contract_app(
            settings=settings,
            services=services.application,
            run_service=services.run,
            review_service=services.review,
        )
        runtime.run_store.recover_interrupted()
        uvicorn.run(app, host=settings.http.host, port=settings.http.port)
    finally:
        if services is not None:
            services.run.close()
        runtime.engine.dispose()
        lock.__exit__(None, None, None)


if __name__ == "__main__":
    main()
