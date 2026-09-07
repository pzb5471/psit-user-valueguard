"""应用工厂：M3 是唯一装配点（技术实施规格第 6、14 节；ADR 0069、0082、0083）。

以显式依赖注入创建 FastAPI，不使用可变全局装配；应用工厂只依赖
配置对象与端口 Protocol，不导入 M1/M2 模块内部实现。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from socket import AF_INET, AF_INET6, SOCK_STREAM, socket

from fastapi import FastAPI

from app.modules.application.app_factory.health import (
    AnalysisHealthPort,
    register_health,
)
from app.modules.application.config.settings import ConfigError, Settings

__all__ = ["PortInUseError", "create_app", "ensure_port_available"]


class PortInUseError(ConfigError):
    """端口被占用；按 ADR 0083 明确停止，不随机换号。"""


def ensure_port_available(host: str, port: int) -> None:
    """预检监听端口；被占用时给出业务可处理的错误而不是随机改绑。"""
    family = AF_INET6 if ":" in host else AF_INET
    with socket(family, SOCK_STREAM) as probe:
        try:
            probe.bind((host, port))
        except OSError as error:
            raise PortInUseError(
                f"端口 {host}:{port} 已被占用；按 ADR 0083 不随机换号，"
                "请在不入 Git 的 config/local.toml 中显式更换端口。"
            ) from error


def create_app(
    settings: Settings,
    analysis_health: AnalysisHealthPort | None = None,
) -> FastAPI:
    """以显式参数装配 FastAPI；缺密钥时应用仍可启动并提供历史只读能力。"""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        runtime_dir = settings.resolve_runtime_dir()
        try:
            runtime_dir.mkdir(parents=True, exist_ok=True)
            probe = runtime_dir / ".startup_write_probe"
            probe.write_text("", encoding="utf-8")
            probe.unlink()
        except OSError as error:
            raise ConfigError(
                f"运行数据目录不可写：{runtime_dir}（{error}）；"
                "ADR 0082 不静默更换目录，请在 config/local.toml 显式调整 storage.runtime_dir。"
            ) from error
        # M3-05 起在此接入 Alembic 迁移与启动恢复（规格 10.5）；M3-08 接入正常关闭（规格 10.6）。
        yield

    app = FastAPI(title="PSIT 高价值客户异常售后决策支持", lifespan=lifespan)
    app.state.settings = settings
    app.state.analysis_health = analysis_health
    register_health(app)
    return app
