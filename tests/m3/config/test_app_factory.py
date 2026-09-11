"""应用工厂测试（M3-02 自动验收：端口冲突、缺密钥、Fake 仅测试注入）。"""

from __future__ import annotations

import socket
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.modules.application.app_factory import (
    PortInUseError,
    create_app,
    ensure_port_available,
)
from app.modules.application.config.settings import Settings

REPO_ROOT = Path(__file__).resolve().parents[3]


def make_settings(base_config: dict[str, Any], **overrides: object) -> Settings:
    config = dict(base_config)
    config.update(overrides)
    return Settings(**config)


class FakeAnalysisHealth:
    """测试边界内的 Fake 健康探针；生产装配永远不会构造它。"""

    def __init__(self, *, available: bool) -> None:
        self.available = available
        self.calls = 0

    def health_check(self) -> bool:
        self.calls += 1
        return self.available


def test_free_port_passes_and_occupied_port_fails_explicitly() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as holder:
        holder.bind(("127.0.0.1", 0))
        holder.listen(1)
        occupied_port = holder.getsockname()[1]
        with pytest.raises(PortInUseError) as exc_info:
            ensure_port_available("127.0.0.1", occupied_port)
        # ADR 0083：不随机换号，错误指明受控出口。
        assert str(exc_info.value).startswith("PORT_IN_USE:")
        assert "不随机换号" in str(exc_info.value)
        assert "local.toml" in str(exc_info.value)


def test_port_zero_always_available() -> None:
    ensure_port_available("127.0.0.1", 0)


def test_missing_key_app_starts_readonly_and_reports_unavailable(
    base_config: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ZAI_API_KEY", raising=False)
    settings = make_settings(base_config)
    app = create_app(settings)
    client = TestClient(app)
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["analysis_status"] == "UNAVAILABLE"
    assert "ZAI_API_KEY" in body["message"]
    assert "历史结果仍可查看" in body["message"]


def test_missing_key_never_switches_to_fake(
    base_config: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """缺密钥且未注入时，analysis_status 必须是 UNAVAILABLE，绝不自动变绿。"""
    monkeypatch.delenv("ZAI_API_KEY", raising=False)
    settings = make_settings(base_config)
    body = TestClient(create_app(settings)).get("/api/v1/health").json()
    assert body["analysis_status"] != "AVAILABLE"


def test_fake_health_injection_only_from_test_boundary(
    base_config: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ZAI_API_KEY", raising=False)
    settings = make_settings(base_config)

    available_fake = FakeAnalysisHealth(available=True)
    body = (
        TestClient(create_app(settings, analysis_health=available_fake))
        .get("/api/v1/health")
        .json()
    )
    assert body["analysis_status"] == "AVAILABLE"
    assert available_fake.calls == 1

    unavailable_fake = FakeAnalysisHealth(available=False)
    body = (
        TestClient(create_app(settings, analysis_health=unavailable_fake))
        .get("/api/v1/health")
        .json()
    )
    assert body["analysis_status"] == "UNAVAILABLE"


def test_env_key_without_production_wiring_remains_unavailable(
    base_config: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ZAI_API_KEY", "test-key-123")
    settings = make_settings(base_config)
    body = TestClient(create_app(settings)).get("/api/v1/health").json()
    assert body["analysis_status"] == "UNAVAILABLE"
    assert "尚未装配" in body["message"]


def test_local_toml_port_flows_into_settings(
    tmp_path: Path, base_config: dict[str, Any]
) -> None:
    local = tmp_path / "local.toml"
    local.write_text("[http]\nport = 8181\n", encoding="utf-8")
    settings = Settings.load(REPO_ROOT, local_toml=local)
    app = create_app(settings)
    assert app.state.settings.http.port == 8181
