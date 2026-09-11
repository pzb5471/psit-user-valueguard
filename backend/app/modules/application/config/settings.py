"""严格运行配置（技术实施规格 3.2、第 14 节；ADR 0047、0082、0083）。

非敏感参数来自进入 Git 的 ``config/default.toml``，成员本机覆盖来自不入
Git 的可选 ``config/local.toml``；两者严格合并校验。配置项缺失、类型错误
或超出范围时立即失败并指出具体项目，不使用隐式默认值带错运行。智谱密钥
只从 ``ZAI_API_KEY`` 环境变量读取，不允许出现在任何 TOML 文件中。
"""

from __future__ import annotations

import ipaddress
import tomllib
from pathlib import Path, PureWindowsPath
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigError(Exception):
    """配置无法满足启动合同；按 ADR 0047 立即停止启动并指出具体项目。"""


def find_project_root() -> Path:
    """按 ADR 0082 把运行数据锚定到项目根目录，而不是执行命令时的当前目录。"""
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "config" / "default.toml").is_file():
            return candidate
    raise ConfigError("未找到 config/default.toml，无法定位项目根目录。")


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except FileNotFoundError as error:
        raise ConfigError(f"缺少配置文件：{path}") from error
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(f"配置文件不是合法 TOML：{path}（{error}）") from error


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> None:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            nested = base[key]
            assert isinstance(nested, dict)
            _deep_merge(nested, value)
        else:
            base[key] = value


class _StrictModel(BaseModel):
    """配置段共用约束：禁止未知键（拼错立即失败），禁止隐式类型转换。"""

    model_config = ConfigDict(extra="forbid", strict=True)


class HttpConfig(_StrictModel):
    """演示服务监听地址（ADR 0083：只允许回环默认与显式本机覆盖）。"""

    host: str
    port: int = Field(ge=1, le=65535)

    @field_validator("host")
    @classmethod
    def _host_must_be_loopback(cls, value: str) -> str:
        try:
            address = ipaddress.ip_address(value)
        except ValueError as error:
            raise ValueError(f"http.host 必须是 IP 地址，收到 {value!r}") from error
        if not address.is_loopback:
            raise ValueError(
                f"http.host 必须是回环地址，收到 {value}；ADR 0083 不允许 0.0.0.0 扩大监听范围"
            )
        return value


class FrontendConfig(_StrictModel):
    """Vite 开发服务器端口（ADR 0083）。"""

    dev_port: int = Field(ge=1, le=65535)


class StorageConfig(_StrictModel):
    """运行数据目录；相对值按项目根目录解析（ADR 0082）。"""

    runtime_dir: str

    @field_validator("runtime_dir")
    @classmethod
    def _reject_unc(cls, value: str) -> str:
        if PureWindowsPath(value).drive.startswith("\\\\"):
            raise ValueError(f"storage.runtime_dir 不允许 UNC 网络路径，收到 {value!r}")
        return value


class AnalysisConfig(_StrictModel):
    """GLM 连接与响应上限（规格 3.2；最终值由 M2-10 PoC 冻结）。"""

    production_enabled: bool
    connect_timeout_seconds: float = Field(gt=0)
    response_timeout_seconds: float = Field(gt=0)
    max_tokens: int = Field(gt=0)


class RetryConfig(_StrictModel):
    max_attempts: int = Field(ge=1)


class ExecutorConfig(_StrictModel):
    """案例并发（规格 3.2：可在 1—3 内配置，最终值由 PoC 决定）。"""

    case_concurrency: int = Field(ge=1, le=3)


class PollingConfig(_StrictModel):
    active_batch_interval_seconds: float = Field(gt=0)


class LoggingConfig(_StrictModel):
    """结构化 JSONL 日志等级（规格 3.2；脱敏与轮换由 M3 后续卡落地）。"""

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class Settings(BaseSettings):
    """集中读取的严格配置；应用工厂以显式参数注入本对象。"""

    model_config = SettingsConfigDict(
        extra="forbid",
        frozen=True,
        case_sensitive=True,
        env_ignore_empty=True,
    )

    http: HttpConfig
    frontend: FrontendConfig
    storage: StorageConfig
    analysis: AnalysisConfig
    retry: RetryConfig
    executor: ExecutorConfig
    polling: PollingConfig
    logging: LoggingConfig

    # 密钥只来自 ZAI_API_KEY 环境变量；缺失时保留历史只读能力（规格第 14 节）。
    zai_api_key: SecretStr | None = Field(default=None, validation_alias="ZAI_API_KEY")

    @classmethod
    def load(
        cls,
        project_root: Path | None = None,
        *,
        local_toml: Path | None = None,
    ) -> Settings:
        """读取 default.toml 并叠加可选 local.toml；密钥由环境变量来源填充。"""
        root = project_root if project_root is not None else find_project_root()
        merged = _read_toml(root / "config" / "default.toml")
        local_path = local_toml if local_toml is not None else root / "config" / "local.toml"
        if local_path.is_file():
            _deep_merge(merged, _read_toml(local_path))
        return cls(**merged)

    def resolve_runtime_dir(self, project_root: Path | None = None) -> Path:
        """把 storage.runtime_dir 解析为绝对路径；相对值按项目根目录解析。"""
        path = Path(self.storage.runtime_dir)
        if not path.is_absolute():
            root = project_root if project_root is not None else find_project_root()
            path = root / path
        return path
