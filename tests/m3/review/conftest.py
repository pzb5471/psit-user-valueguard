"""M3-07 审核测试夹具：复用 run_service 的 FakeRunQuery + FakeReviewStore。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "run_service"))

import pytest
from review_fakes import FakeReviewStore
from run_fakes import FakeRunQuery

from app.modules.application.review import ReviewService


@pytest.fixture()
def review_store() -> FakeReviewStore:
    return FakeReviewStore()


@pytest.fixture()
def query() -> FakeRunQuery:
    return FakeRunQuery(current_case_run_id=1)


@pytest.fixture()
def service(review_store: FakeReviewStore, query: FakeRunQuery) -> ReviewService:
    return ReviewService(query=query, review_store=review_store)


@pytest.fixture()
def app(service: ReviewService):

    from fastapi.testclient import TestClient

    from app.modules.application.api.router import create_contract_app

    test_app = create_contract_app(review_service=service)
    with TestClient(test_app) as client:
        yield client
