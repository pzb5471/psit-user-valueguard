"""M1-02 测试公共夹具：每次测试独立临时 SQLite 空库并升到 Alembic head。

技术实施规格 16.4 M1-02 自动验收要求"空库升级、重复升级、外键、唯一约束、
活动运行约束和九表字段快照全部通过"。本文件用 PSIT_DB_URL 把 Alembic 指向
临时数据库文件（env.py 已支持该环境变量），并默认开启 SQLite 外键强制。
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Connection, Engine

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
def migrate() -> Callable[[Path], None]:
    """对给定 SQLite 文件执行 alembic upgrade head。"""
    return _run_migrations


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
def conn(engine: Engine) -> Iterator[Connection]:
    """引擎自带事务的连接；违反约束后用 begin_nested() 回滚到保存点。"""
    with engine.begin() as connection:
        yield connection
