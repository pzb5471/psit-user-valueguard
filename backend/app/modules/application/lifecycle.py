"""M3-08 真实运行时生命周期适配。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.modules.application.config.settings import Settings
from app.modules.application.wiring import RealRuntime, build_runtime, instance_lock


@asynccontextmanager
async def runtime_lifespan(
    app: FastAPI,
    *,
    settings: Settings,
    runtime: RealRuntime,
) -> AsyncIterator[None]:
    """持有单实例锁，执行恢复检查；关闭时等待后台服务并释放资源。"""
    lock = instance_lock(runtime.runtime_dir)
    lock.__enter__()
    try:
        runtime.run_store.recover_interrupted()
        yield
    finally:
        run_service = getattr(app.state, "run_service", None)
        if run_service is not None:
            run_service.close()
        runtime.engine.dispose()
        lock.__exit__(None, None, None)


def acquire_runtime(settings: Settings) -> RealRuntime:
    """创建并迁移真实运行时；调用方负责在生命周期内持有锁。"""
    return build_runtime(settings.resolve_runtime_dir())
