"""M3-04 测试夹具：Fake M1 端口 + 注入服务的合同应用。"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fakes import FakeEvidence, FakeImporter, FakeQuery
from fastapi.testclient import TestClient

from app.modules.application.api.router import create_contract_app
from app.modules.application.services.query import ApplicationServices, M1Ports


@pytest.fixture()
def importer() -> FakeImporter:
    return FakeImporter()


@pytest.fixture()
def query() -> FakeQuery:
    return FakeQuery()


@pytest.fixture()
def evidence() -> FakeEvidence:
    return FakeEvidence()


@pytest.fixture()
def client(
    importer: FakeImporter,
    query: FakeQuery,
    evidence: FakeEvidence,
) -> Iterator[TestClient]:
    ports = M1Ports(importer=importer, query=query, evidence=evidence)
    services = ApplicationServices(ports)
    app = create_contract_app(services=services)
    with TestClient(app) as test_client:
        yield test_client
