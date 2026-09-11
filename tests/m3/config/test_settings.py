"""严格配置测试（M3-02 自动验收：默认与本机覆盖、非法类型、缺密钥）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.modules.application.config.settings import (
    ConfigError,
    Settings,
    find_project_root,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def write_toml(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def test_default_toml_matches_spec_3_2_defaults() -> None:
    settings = Settings.load(REPO_ROOT)
    assert settings.http.host == "127.0.0.1"
    assert settings.http.port == 8000
    assert settings.frontend.dev_port == 5173
    assert settings.analysis.connect_timeout_seconds == 10
    assert settings.analysis.response_timeout_seconds == 300
    assert settings.analysis.max_tokens == 4096
    assert settings.analysis.production_enabled is True
    assert settings.retry.max_attempts == 3
    assert settings.executor.case_concurrency == 2
    assert settings.polling.active_batch_interval_seconds == 2
    assert settings.logging.level == "INFO"


def test_local_override_applies_without_touching_other_sections(
    tmp_path: Path, base_config: dict[str, Any]
) -> None:
    local = write_toml(
        tmp_path / "local.toml",
        "\n".join(
            [
                "[http]",
                'port = 8123',
                "[executor]",
                "case_concurrency = 3",
            ]
        )
        + "\n",
    )
    settings = Settings.load(REPO_ROOT, local_toml=local)
    assert settings.http.port == 8123
    assert settings.http.host == "127.0.0.1"
    assert settings.executor.case_concurrency == 3
    assert settings.frontend.dev_port == 5173


def test_invalid_type_fails_and_names_the_item(
    tmp_path: Path, base_config: dict[str, Any]
) -> None:
    base_config["http"] = {"host": "127.0.0.1", "port": "8000"}
    with pytest.raises(ValidationError) as exc_info:
        Settings(**base_config)
    assert "http.port" in str(exc_info.value)


def test_bool_is_not_a_valid_port_in_strict_mode(
    base_config: dict[str, Any],
) -> None:
    base_config["http"] = {"host": "127.0.0.1", "port": True}
    with pytest.raises(ValidationError):
        Settings(**base_config)


@pytest.mark.parametrize("bad_concurrency", [0, 4])
def test_case_concurrency_out_of_range_fails(
    base_config: dict[str, Any], bad_concurrency: int
) -> None:
    base_config["executor"] = {"case_concurrency": bad_concurrency}
    with pytest.raises(ValidationError) as exc_info:
        Settings(**base_config)
    assert "case_concurrency" in str(exc_info.value)


def test_unknown_config_item_fails(base_config: dict[str, Any]) -> None:
    base_config["logging"] = {"level": "INFO", "verbose": True}
    with pytest.raises(ValidationError) as exc_info:
        Settings(**base_config)
    assert "verbose" in str(exc_info.value)


def test_missing_section_fails_without_implicit_defaults(
    base_config: dict[str, Any],
) -> None:
    del base_config["polling"]
    with pytest.raises(ValidationError) as exc_info:
        Settings(**base_config)
    assert "polling" in str(exc_info.value)


def test_non_loopback_host_is_rejected(base_config: dict[str, Any]) -> None:
    base_config["http"] = {"host": "0.0.0.0", "port": 8000}
    with pytest.raises(ValidationError) as exc_info:
        Settings(**base_config)
    assert "回环" in str(exc_info.value)


def test_unc_runtime_dir_is_rejected(base_config: dict[str, Any]) -> None:
    base_config["storage"] = {"runtime_dir": r"\\server\share\runtime"}
    with pytest.raises(ValidationError) as exc_info:
        Settings(**base_config)
    assert "UNC" in str(exc_info.value)


def test_missing_api_key_stays_none_and_env_key_is_captured(
    base_config: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ZAI_API_KEY", raising=False)
    settings = Settings(**base_config)
    assert settings.zai_api_key is None

    monkeypatch.setenv("ZAI_API_KEY", "test-key-123")
    settings = Settings(**base_config)
    assert settings.zai_api_key is not None
    assert settings.zai_api_key.get_secret_value() == "test-key-123"
    # 密钥不进入任何普通字符串表示（禁止把密钥写入日志或业务响应）。
    assert "test-key-123" not in str(settings)


def test_default_toml_contains_no_key_material() -> None:
    import tomllib

    with (REPO_ROOT / "config" / "default.toml").open("rb") as handle:
        data = tomllib.load(handle)

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                assert "api_key" not in key.lower()
                walk(value)

    walk(data)


def test_relative_runtime_dir_resolves_against_project_root(
    tmp_path: Path, base_config: dict[str, Any]
) -> None:
    settings = Settings(**base_config)
    assert settings.resolve_runtime_dir(tmp_path) == tmp_path / "runtime_data"
    assert settings.resolve_runtime_dir() == Path(find_project_root()) / "runtime_data"


def test_missing_default_toml_reports_explicit_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as exc_info:
        Settings.load(tmp_path)
    assert "default.toml" in str(exc_info.value)
