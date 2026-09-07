"""M3-06 单案例重跑测试：202、禁止转换、并发冲突、旧历史与计数、首次历史不变。"""

from __future__ import annotations

from fastapi.testclient import TestClient
from run_fakes import make_detail, make_failure, make_queue, make_success, make_workspace

from app.modules.application.api.contracts.errors import ApiErrorCode
from app.modules.application.api.router import create_contract_app
from app.modules.application.services.query.errors import ServiceError


def _assert_service_error(error: ServiceError, code: ApiErrorCode) -> None:
    assert error.code == code


def test_rerun_pending_review_returns_202(query, engine, service_factory) -> None:
    query.detail = make_detail(status="PENDING_REVIEW")
    query.workspace = make_workspace("b1", status="PENDING_REVIEW", case_count=1)
    query.queue = make_queue("b1", case_ids=["c1"])
    service = service_factory()
    view = service.rerun_case("b1", "c1")
    service.close()
    assert view.case_id == "c1"


def test_rerun_uses_manual_trigger_without_batch_history(
    run_store, query, engine, service_factory
) -> None:
    query.detail = make_detail(status="PENDING_REVIEW")
    query.workspace = make_workspace("b1", status="PENDING_REVIEW", case_count=1)
    query.queue = make_queue("b1", case_ids=["c1"])
    service = service_factory()
    service.rerun_case("b1", "c1")
    service.close()
    # 重跑创建新的 MANUAL_RERUN 案例运行，且不关联首次批次运行（旧历史保留）。
    assert any("create_case_run:c1" in c for c in run_store.calls)
    assert not any(c.startswith("finish:") for c in run_store.calls)  # 首次批次历史不变


def test_rerun_rejects_pending_analysis(query, engine, service_factory) -> None:
    query.detail = make_detail(status="PENDING_ANALYSIS")
    query.workspace = make_workspace("b1", status="PENDING_ANALYSIS", case_count=1)
    query.queue = make_queue("b1", case_ids=["c1"])
    service = service_factory()
    try:
        service.rerun_case("b1", "c1")
        assert False, "PENDING_ANALYSIS 不应允许重跑"
    except ServiceError as error:
        _assert_service_error(error, ApiErrorCode.CASE_NOT_RERUNNABLE)
    finally:
        service.close()


def test_rerun_rejects_completed(query, engine, service_factory) -> None:
    query.detail = make_detail(status="COMPLETED")
    query.workspace = make_workspace("b1", status="COMPLETED", case_count=1)
    query.queue = make_queue("b1", case_ids=["c1"])
    service = service_factory()
    try:
        service.rerun_case("b1", "c1")
        assert False, "COMPLETED 不应允许重跑"
    except ServiceError as error:
        _assert_service_error(error, ApiErrorCode.CASE_ALREADY_COMPLETED)
    finally:
        service.close()


def test_rerun_concurrency_conflict(run_store, query, engine, service_factory) -> None:
    query.detail = make_detail(status="PROCESSING_ERROR")
    query.workspace = make_workspace("b1", status="PROCESSING_ERROR", case_count=1)
    query.queue = make_queue("b1", case_ids=["c1"])
    run_store.reject_case = True  # 已有活动案例运行
    service = service_factory()
    try:
        service.rerun_case("b1", "c1")
        assert False, "并发重跑应冲突"
    except ServiceError as error:
        _assert_service_error(error, ApiErrorCode.ACTIVE_CASE_RUN_EXISTS)
    finally:
        service.close()


def test_rerun_success_updates_projection(run_store, query, engine, service_factory) -> None:
    query.detail = make_detail(status="PENDING_REVIEW")
    query.workspace = make_workspace("b1", status="PENDING_REVIEW", case_count=1)
    query.queue = make_queue("b1", case_ids=["c1"])
    engine.outcomes = {"c1": make_success("c1")}
    service = service_factory()
    service.rerun_case("b1", "c1")
    service.close()
    assert any(c.startswith("publish:") for c in run_store.calls)
    assert run_store.published == 1  # 成功计数 +1


def test_rerun_failure_updates_error_count(run_store, query, engine, service_factory) -> None:
    query.detail = make_detail(status="PROCESSING_ERROR")
    query.workspace = make_workspace("b1", status="PROCESSING_ERROR", case_count=1)
    query.queue = make_queue("b1", case_ids=["c1"])
    engine.outcomes = {"c1": make_failure("c1")}
    service = service_factory()
    service.rerun_case("b1", "c1")
    service.close()
    assert any(c.startswith("failure:") for c in run_store.calls)
    assert run_store.failed == 1


def test_rerun_202_via_route(query, engine, service_factory) -> None:
    query.detail = make_detail(status="PROCESSING_ERROR")
    query.workspace = make_workspace("b1", status="PROCESSING_ERROR", case_count=1)
    query.queue = make_queue("b1", case_ids=["c1"])
    service = service_factory()
    app = create_contract_app(run_service=service)
    with TestClient(app) as client:
        response = client.post("/api/v1/batches/b1/cases/c1/reruns")
        assert response.status_code == 202
        assert response.json()["case_id"] == "c1"
    service.close()
