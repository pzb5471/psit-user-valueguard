"""M3-05 批次开始编排测试：202、幂等、单活动批次、每案例单运行。"""

from __future__ import annotations

from fastapi.testclient import TestClient
from run_fakes import make_queue, make_workspace

from app.modules.application.api.contracts.errors import ApiErrorCode
from app.modules.application.api.router import create_contract_app
from app.modules.application.services.query.errors import ServiceError


def test_start_batch_run_returns_view(run_store, engine, run_query, service_factory) -> None:
    run_query.workspace = make_workspace("b1", case_count=2)
    run_query.queue = make_queue("b1", case_ids=["c1", "c2"])
    service = service_factory()
    view = service.start_batch_run("b1")
    service.close()  # 等待后台案例完成
    assert view.batch_id == "b1"
    assert "create_batch_run:b1" in run_store.calls
    assert "create_case_run:c1" in run_store.calls
    assert "create_case_run:c2" in run_store.calls
    assert run_store.calls.count("create_batch_run:b1") == 1  # 一个活动批次


def test_unavailable_analysis_rejects_start_without_writes(
    run_store, engine, run_query, service_factory
) -> None:
    run_query.workspace = make_workspace("b1", case_count=1)
    service = service_factory(
        analysis_available=False,
        analysis_unavailable_message="真实分析引擎尚未装配",
    )

    try:
        service.start_batch_run("b1")
        assert False, "应当抛出 ANALYSIS_UNAVAILABLE"
    except ServiceError as error:
        assert error.code == ApiErrorCode.ANALYSIS_UNAVAILABLE
        assert error.message == "真实分析引擎尚未装配"
        assert run_store.calls == []
        assert engine.requests == []
    finally:
        service.close()


def test_start_creates_one_case_run_per_case(run_store, engine, run_query, service_factory) -> None:
    run_query.queue = make_queue("b1", case_ids=["c1", "c2", "c3"])
    run_query.workspace = make_workspace("b1", case_count=3)
    service = service_factory()
    service.start_batch_run("b1")
    service.close()
    assert run_store.calls.count("create_case_run:c1") == 1
    assert run_store.calls.count("create_case_run:c2") == 1
    assert run_store.calls.count("create_case_run:c3") == 1


def test_start_batch_run_202_via_route(run_store, engine, run_query, service_factory) -> None:
    run_query.workspace = make_workspace("b1", case_count=1)
    run_query.queue = make_queue("b1", case_ids=["c1"])
    service = service_factory()
    app = create_contract_app(run_service=service)
    with TestClient(app) as client:
        response = client.post("/api/v1/batches/b1/runs")
        assert response.status_code == 202
        assert response.json()["batch_id"] == "b1"
    service.close()


def test_duplicate_start_idempotent_when_batch_analyzing(
    run_store, engine, run_query, service_factory
) -> None:
    run_query.workspace = make_workspace("b1", status="ANALYZING", case_count=2)
    run_query.queue = make_queue("b1", case_ids=["c1", "c2"])
    service = service_factory()
    service.start_batch_run("b1")  # 幂等命中，不再创建批次运行
    service.close()
    assert "create_batch_run:b1" not in run_store.calls


def test_active_batch_conflict_returns_409(
    run_store, engine, run_query, service_factory
) -> None:
    run_store.reject_start = True
    service = service_factory()
    try:
        service.start_batch_run("b1")
        assert False, "应当抛出 ACTIVE_BATCH_EXISTS"
    except ServiceError as error:
        assert error.code == ApiErrorCode.ACTIVE_BATCH_EXISTS
    finally:
        service.close()
