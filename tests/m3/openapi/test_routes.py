"""十个固定接口的方法、路径、成功码与允许状态码（M3-03 自动验收）。

断言从 OpenAPI schema 提取——它是本卡的产出真源，且不受 FastAPI
版本将 include_router 惰性化为 _IncludedRouter 的影响。
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI

EXPECTED_ROUTES: dict[tuple[str, str], set[int]] = {
    ("POST", "/api/v1/batches"): {200, 201},
    ("GET", "/api/v1/batches"): {200},
    ("GET", "/api/v1/batches/{batch_id}"): {200},
    ("POST", "/api/v1/batches/{batch_id}/runs"): {202},
    ("GET", "/api/v1/batches/{batch_id}/cases"): {200},
    ("GET", "/api/v1/batches/{batch_id}/cases/{case_id}"): {200},
    ("POST", "/api/v1/batches/{batch_id}/cases/{case_id}/reruns"): {202},
    ("POST", "/api/v1/batches/{batch_id}/cases/{case_id}/reviews"): {200, 201},
    (
        "GET",
        "/api/v1/batches/{batch_id}/cases/{case_id}/evidence/{evidence_id}/content",
    ): {200},
    ("GET", "/api/v1/health"): {200},
}

#: HTTP 只使用这十一个状态码（规格 12.4）。
ALLOWED_STATUS_CODES = {200, 201, 202, 400, 404, 409, 413, 415, 422, 500, 503}

HTTP_METHODS = {"get", "post", "put", "delete", "patch"}


def declared_routes(contract_app: FastAPI) -> dict[tuple[str, str], set[int]]:
    schema = contract_app.openapi()
    routes: dict[tuple[str, str], set[int]] = {}
    for path, operations in schema["paths"].items():
        for method, operation in operations.items():
            if method in HTTP_METHODS:
                responses: dict[str, Any] = operation["responses"]
                routes[(method.upper(), path)] = {
                    int(code) for code in responses if code.isdigit()
                }
    return routes


def test_exactly_ten_frozen_routes(contract_app: FastAPI) -> None:
    assert set(declared_routes(contract_app)) == set(EXPECTED_ROUTES)


def test_every_route_declares_its_success_codes(contract_app: FastAPI) -> None:
    routes = declared_routes(contract_app)
    for key, success_codes in EXPECTED_ROUTES.items():
        declared = routes[key]
        assert success_codes <= declared, f"{key} 缺少成功码 {success_codes - declared}"


def test_declared_status_codes_stay_in_http_whitelist(contract_app: FastAPI) -> None:
    for key, declared in declared_routes(contract_app).items():
        assert declared <= ALLOWED_STATUS_CODES, f"{key} 声明了白名单外状态码"


def test_upload_and_reviews_declare_dual_success(contract_app: FastAPI) -> None:
    routes = declared_routes(contract_app)
    assert {200, 201} <= routes[("POST", "/api/v1/batches")]  # 重复包幂等命中
    assert {200, 201} <= routes[
        ("POST", "/api/v1/batches/{batch_id}/cases/{case_id}/reviews")
    ]


def test_start_and_rerun_have_no_request_body(contract_app: FastAPI) -> None:
    schema = contract_app.openapi()
    for path in (
        "/api/v1/batches/{batch_id}/runs",
        "/api/v1/batches/{batch_id}/cases/{case_id}/reruns",
    ):
        assert "requestBody" not in schema["paths"][path]["post"], (
            f"{path} 不得有请求体；模型参数、并发、Prompt 和运行编号不能由页面传入"
        )


def test_case_list_has_fixed_server_sorting_only(contract_app: FastAPI) -> None:
    """案例列表查询参数只暴露 status、intervention_level、limit、offset。"""
    schema = contract_app.openapi()
    params = schema["paths"]["/api/v1/batches/{batch_id}/cases"]["get"]["parameters"]
    query_names = {param["name"] for param in params if param["in"] == "query"}
    assert query_names == {"status", "intervention_level", "limit", "offset"}
    assert "sort_by" not in query_names
