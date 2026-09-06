"""M1-06 公共夹具：独立临时 SQLite 空库、运行数据根、导入网关与证据网关。

复用 M1-03/04 的迁移（Alembic head）、外键强制与目录约定（规格 11.3 /
ADR-0033）：formal_root 指向临时运行数据根，其下 batches/<batch_id>/
<data_version>/ 为正式批次目录；tmp_root 为独立临时导入根。evidence_gateway
注入 EvidenceGateway（同一 formal_root，读取已落盘的正式证据文件）。
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine

from app.modules.data.evidence.gateway import EvidenceGateway
from app.modules.data.importing.gateway import BatchImportGateway

BACKEND_DIR = Path(__file__).resolve().parents[3] / "backend"
ALEMBIC_INI = BACKEND_DIR / "alembic" / "alembic.ini"


def _run_migrations(db_path: Path) -> None:
    """在给定 SQLite 文件上执行 alembic upgrade head（PSIT_DB_URL 覆盖默认库）。"""
    cfg = Config(str(ALEMBIC_INI))
    previous = os.environ.get("PSIT_DB_URL")
    os.environ["PSIT_DB_URL"] = f"sqlite:///{db_path.as_posix()}"
    try:
        command.upgrade(cfg, "head")
    finally:
        if previous is None:
            os.environ.pop("PSIT_DB_URL", None)
        else:
            os.environ["PSIT_DB_URL"] = previous


def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:  # pragma: no cover
    """SQLite 默认不强制外键；按规格 11.2 保存规则每次连接显式开启。"""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """每次测试独立的临时 SQLite 文件路径（开始时不存在）。"""
    return tmp_path / "psit.db"


@pytest.fixture
def engine(db_path: Path) -> Iterator[Engine]:
    """已经迁移到 head 并开启外键强制的 SQLite 引擎。"""
    _run_migrations(db_path)
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    event.listen(engine, "connect", _enable_foreign_keys)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def formal_root(tmp_path: Path) -> Path:
    """临时运行数据根；正式批次目录为 formal_root/batches/<batch_id>/<data_version>/。"""
    return tmp_path / "runtime_data"


@pytest.fixture
def tmp_root(tmp_path: Path) -> Path:
    """独立临时导入根（规格 11.3 imports/tmp/）。"""
    return tmp_path / "runtime_data" / "imports" / "tmp"


@pytest.fixture
def gateway(engine: Engine, formal_root: Path, tmp_root: Path) -> BatchImportGateway:
    """注入独立库、独立运行数据根与默认上限的 BatchImportGateway。"""
    return BatchImportGateway(engine=engine, formal_root=formal_root, tmp_root=tmp_root)


@pytest.fixture
def evidence_gateway(engine: Engine, formal_root: Path) -> EvidenceGateway:
    """注入独立库与同一正式运行数据根的 EvidenceGateway。"""
    return EvidenceGateway(engine=engine, formal_root=formal_root)
