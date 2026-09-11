"""本机生产启动入口：真实 GLM 受 M2-10 显式门禁控制。"""

from __future__ import annotations

import sys

import uvicorn

from app.modules.application.api.router import create_contract_app
from app.modules.application.app_factory import PortInUseError, ensure_port_available
from app.modules.application.config.settings import Settings, find_project_root
from app.modules.application.production_analysis import build_production_analysis
from app.modules.application.static_frontend import mount_frontend
from app.modules.application.wiring import (
    SingletonLockError,
    build_runtime,
    build_services,
    instance_lock,
)


def run() -> None:
    settings = Settings.load()
    ensure_port_available(settings.http.host, settings.http.port)
    runtime_dir = settings.resolve_runtime_dir()
    with instance_lock(runtime_dir):
        runtime = build_runtime(runtime_dir)
        services = None
        try:
            analysis = build_production_analysis(settings, runtime_root=runtime_dir)
            services = build_services(
                runtime,
                analysis_engine=analysis.engine,
                max_concurrency=settings.executor.case_concurrency,
                analysis_available=analysis.available,
                analysis_unavailable_message=analysis.message,
            )
            app = create_contract_app(
                settings=settings,
                services=services.application,
                run_service=services.run,
                review_service=services.review,
            )
            app.state.analysis_health = analysis.health
            mount_frontend(app, find_project_root() / "frontend" / "dist")
            runtime.run_store.recover_interrupted()
            uvicorn.run(app, host=settings.http.host, port=settings.http.port)
        finally:
            if services is not None:
                services.run.close(interrupt=True)
            runtime.engine.dispose()


def main() -> int:
    try:
        run()
    except PortInUseError as error:
        print(error, file=sys.stderr)
        return 3
    except SingletonLockError as error:
        print(f"INSTANCE_ALREADY_RUNNING: {error}", file=sys.stderr)
        return 4
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
