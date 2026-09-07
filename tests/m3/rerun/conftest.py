"""M3-06 重跑测试夹具：复用 M3-05 的 Fake M1/M2（run_fakes）。"""

from __future__ import annotations

import sys
from pathlib import Path

# 让本目录测试可导入 run_service 目录下的共享 Fake（run_fakes）。
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "run_service"))

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
def query(run_store: FakeRunStore) -> FakeRunQuery:
    return FakeRunQuery(run_store=run_store)


@pytest.fixture()
def service_factory(
    run_store: FakeRunStore, engine: FakeEngine, query: FakeRunQuery
):
    def build(**kwargs):
        return RunService(
            run_store=run_store,
            analysis_engine=engine,
            query=query,
            versions=AnalysisVersionConfig(**make_versions()),
            max_concurrency=kwargs.get("max_concurrency", 2),
        )

    return build
