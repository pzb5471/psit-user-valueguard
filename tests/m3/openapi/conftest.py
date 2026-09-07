"""M3-03 合同测试夹具：组合十个接口的合同应用与测试客户端。"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.modules.application.api.router import create_contract_app


@pytest.fixture()
def contract_app() -> FastAPI:
    return create_contract_app()


@pytest.fixture()
def client(contract_app: FastAPI) -> Iterator[TestClient]:
    with TestClient(contract_app) as test_client:
        yield test_client
