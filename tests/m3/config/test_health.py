"""HealthView 白名单测试（M3-02 自动验收：规格 12.2 字段白名单）。"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.modules.application.app_factory import HealthView, create_app
from app.modules.application.config.settings import Settings


def test_health_response_is_exactly_the_frozen_whitelist(
    base_config: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ZAI_API_KEY", raising=False)
    settings = Settings(**base_config)
    response = TestClient(create_app(settings)).get("/api/v1/health")

    assert response.status_code == 200
    assert set(response.json()) == {
        "app_status",
        "database_status",
        "analysis_status",
        "message",
    }
    body = response.json()
    assert body["app_status"] == "READY"
    assert body["database_status"] == "READY"
    assert body["analysis_status"] in {"AVAILABLE", "UNAVAILABLE"}


def test_health_never_echoes_key_material(
    base_config: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    sentinel = "sk-zai-secret-sentinel-9f3a"
    monkeypatch.setenv("ZAI_API_KEY", sentinel)
    settings = Settings(**base_config)
    response = TestClient(create_app(settings)).get("/api/v1/health")
    assert response.status_code == 200
    assert sentinel not in response.text


def test_health_model_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        HealthView.model_validate(
            {
                "app_status": "READY",
                "database_status": "READY",
                "analysis_status": "AVAILABLE",
                "message": "ok",
                "trace_id": "should-not-exist",
            }
        )


def test_health_route_is_the_tenth_frozen_endpoint_path(
    base_config: dict[str, Any],
) -> None:
    app = create_app(Settings(**base_config))
    route_paths = {str(getattr(route, "path", "")) for route in app.routes}
    assert "/api/v1/health" in route_paths
