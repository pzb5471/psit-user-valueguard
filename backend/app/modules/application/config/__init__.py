"""M3 严格运行配置（ADR 0047：受校验的 TOML 配置与环境变量密钥）。"""

from app.modules.application.config.settings import (
    ConfigError,
    Settings,
)

__all__ = ["ConfigError", "Settings"]
