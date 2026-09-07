"""M1-02 迁移动态测试：空库升级、重复升级与真实 SQLite 结构核对。

技术实施规格 16.4 M1-02 自动验收要求"空库升级、重复升级、外键、唯一约束、
活动运行约束和九表字段快照全部通过"。本文件覆盖：
- 空库 upgrade head 后恰好九张业务表 + alembic_version；
- 重复 upgrade 幂等，版本号仍是 head 且只有一行；
- 真库列名/可空性与模型元数据一致（迁移文件和 models.py 不漂移）；
- SQLite 建表 DDL 中的 CHECK 约束与两个部分唯一索引真实存在。
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import Enum as SAEnum
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.sql.schema import Column

from app.modules.data.db.models import Base

BACKEND_DIR = Path(__file__).resolve().parents[3] / "backend"
ALEMBIC_INI = BACKEND_DIR / "alembic" / "alembic.ini"

HEAD_REVISION = "dc4c1050e0af"

ENUM_COLUMN_NAMES = {
    "batches": {"status"},
    "cases": {"status", "system_intervention_level", "final_intervention_level"},
    "batch_runs": {"status"},
    "case_runs": {"trigger_type", "status"},
    "reviews": {"outcome", "final_intervention_level"},
}


def _open(db_path: Path) -> Engine:
    return create_engine(f"sqlite:///{db_path.as_posix()}")


def _compact(sql: str) -> str:
    return "".join(sql.split())


def test_fresh_upgrade_creates_nine_tables(migrate, db_path: Path) -> None:
    migrate(db_path)
    engine = _open(db_path)
    with engine.connect() as connection:
        tables = set(inspect(connection).get_table_names())
    engine.dispose()
    assert tables == set(Base.metadata.tables) | {"alembic_version"}


def test_repeated_upgrade_is_idempotent(migrate, db_path: Path) -> None:
    migrate(db_path)
    migrate(db_path)  # 第二次应为 no-op，不抛错
    engine = _open(db_path)
    with engine.connect() as connection:
        tables = set(inspect(connection).get_table_names())
        versions = connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).fetchall()
    engine.dispose()
    assert tables == set(Base.metadata.tables) | {"alembic_version"}
    assert versions == [(HEAD_REVISION,)]


def test_db_schema_matches_models(migrate, db_path: Path) -> None:
    migrate(db_path)
    engine = _open(db_path)
    with engine.connect() as connection:
        inspector = inspect(connection)
        for table_name, table in Base.metadata.tables.items():
            columns = {column["name"]: column for column in inspector.get_columns(table_name)}
            assert set(columns) == set(table.columns.keys()), table_name
            for column_name, model_column in table.columns.items():
                assert columns[column_name]["nullable"] == model_column.nullable, (
                    f"{table_name}.{column_name}"
                )
    engine.dispose()


def test_db_schema_has_no_extra_columns(migrate, db_path: Path) -> None:
    """真实迁移后每张表列数与模型一致（防迁移文件擅自增删列）。"""
    migrate(db_path)
    engine = _open(db_path)
    with engine.connect() as connection:
        inspector = inspect(connection)
        for table_name, table in Base.metadata.tables.items():
            db_columns = {column["name"] for column in inspector.get_columns(table_name)}
            assert db_columns == {column.name for column in table.columns}, table_name
    engine.dispose()


def test_check_constraints_present_in_ddl(migrate, db_path: Path) -> None:
    migrate(db_path)
    engine = _open(db_path)
    with engine.connect() as connection:
        ddl_rows = connection.execute(
            text("SELECT name, sql FROM sqlite_master WHERE type = 'table'")
        ).all()
        ddl_by_table: dict[str, str] = {str(row[0]): str(row[1]) for row in ddl_rows}
    engine.dispose()
    for table_name, column_names in ENUM_COLUMN_NAMES.items():
        ddl = _compact(ddl_by_table[table_name])
        for column_name in column_names:
            column: Column = Base.metadata.tables[table_name].columns[column_name]
            constraint_name = f"{table_name}_{column_name}"
            assert f"CONSTRAINT{constraint_name}CHECK" in ddl, (
                f"{table_name}.{column_name} 缺少 CHECK 约束"
            )
            column_type = column.type
            assert isinstance(column_type, SAEnum)
            for value in column_type.enums:
                assert repr(value) in ddl, f"{table_name}.{column_name} 缺少枚举值 {value}"


def test_partial_unique_indexes_present_in_db(migrate, db_path: Path) -> None:
    migrate(db_path)
    engine = _open(db_path)
    with engine.connect() as connection:
        index_rows = connection.execute(
            text("SELECT name, sql FROM sqlite_master WHERE type = 'index'")
        ).all()
        indexes: dict[str, str] = {str(row[0]): str(row[1]) for row in index_rows}
    engine.dispose()

    batch_sql = _compact(indexes["uq_batch_runs_one_active"])
    assert "CREATEUNIQUEINDEXuq_batch_runs_one_activeONbatch_runs" in batch_sql
    assert "WHEREstatusIN('STARTING','RUNNING')" in batch_sql

    case_sql = _compact(indexes["uq_case_runs_one_active_per_case"])
    assert "CREATEUNIQUEINDEXuq_case_runs_one_active_per_caseONcase_runs" in case_sql
    assert (
        "WHEREstatusIN('STARTING','PERCEPTION_RUNNING','ATTRIBUTION_RUNNING',"
        "'STRATEGY_RUNNING')" in case_sql
    )


def test_alembic_config_is_ascii() -> None:
    # GBK locale 下 alembic.ini 含中文会崩溃；迁移配置必须保持纯 ASCII。
    ALEMBIC_INI.read_text(encoding="ascii")
