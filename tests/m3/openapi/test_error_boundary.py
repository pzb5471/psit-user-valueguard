"""错误边界：FastAPI 默认 422 与未处理 500 转换为 BusinessError（M3-03 自动验收）。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.modules.application.api.contracts.errors import BusinessError
from app.modules.application.api.router import create_contract_app

BUSINESS_ERROR_KEYS = {
    "code",
    "message",
    "object_type",
    "object_id",
    "stage",
    "next_action",
    "trace_id",
}


def test_validation_error_becomes_business_error(
    client: TestClient,
) -> None:
    response = client.get("/api/v1/batches", params={"limit": 0})
    assert response.status_code == 422
    body = response.json()
    assert set(body) == BUSINESS_ERROR_KEYS
    assert body["code"] == "REQUEST_VALIDATION_FAILED"
    assert "detail" not in body  # 不得返回 FastAPI 默认 detail


def test_unhandled_exception_becomes_internal_error() -> None:
    app = create_contract_app()

    @app.get("/api/v1/_boom")
    def boom() -> None:
        raise RuntimeError("不应透传的内部细节")

    with TestClient(app, raise_server_exceptions=False) as test_client:
        response = test_client.get("/api/v1/_boom")
    assert response.status_code == 500
    body = response.json()
    assert set(body) == BUSINESS_ERROR_KEYS
    assert body["code"] == "INTERNAL_ERROR"
    assert "不应透传的内部细节" not in response.text
    assert "RuntimeError" not in response.text


def test_business_error_never_revealed_as_default_detail() -> None:
    """BusinessError 自身的对外形态与 OpenAPI 声明一致。"""
    assert set(BusinessError.model_fields) == BUSINESS_ERROR_KEYS - {"object_id"} | {
        "object_id"
    }


def test_health_still_serves_in_contract_app(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert set(response.json()) == {
        "app_status",
        "database_status",
        "analysis_status",
        "message",
    }
