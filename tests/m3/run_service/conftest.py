"""M3-05 RunService 测试夹具。"""

from __future__ import annotations

import pytest
from run_fakes import FakeEngine, FakeRunQuery, FakeRunStore, make_versions

from app.modules.application.run_service import RunService
from app.modules.application.run_service.versions import AnalysisVersionConfig


@pytest.fixture()
def run_store() -> FakeRunStore:
    return FakeRunStore()


@pytest.fixture()
def engine() -> FakeEngine:
    return FakeEngine()


@pytest.fixture()
def run_query(run_store: FakeRunStore) -> FakeRunQuery:
    return FakeRunQuery(run_store=run_store)


def build_service(
    run_store: FakeRunStore,
    engine: FakeEngine,
    run_query: FakeRunQuery,
    *,
    max_concurrency: int = 2,
    analysis_available: bool = True,
    analysis_unavailable_message: str | None = None,
) -> RunService:
    return RunService(
        run_store=run_store,
        analysis_engine=engine,
        query=run_query,
        versions=AnalysisVersionConfig(**make_versions()),
        max_concurrency=max_concurrency,
        analysis_available=analysis_available,
        analysis_unavailable_message=analysis_unavailable_message,
    )


@pytest.fixture()
def service_factory(
    run_store: FakeRunStore, engine: FakeEngine, run_query: FakeRunQuery
):
    return lambda **kw: build_service(run_store, engine, run_query, **kw)
