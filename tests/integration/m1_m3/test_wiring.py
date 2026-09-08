"""M3-08 真实 M1 装配集成测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.modules.application.wiring import (
    SingletonLockError,
    build_runtime,
    instance_lock,
)


def test_build_runtime_runs_sqlite_migrations(tmp_path: Path) -> None:
    runtime = build_runtime(tmp_path / "runtime_data")
    try:
        assert runtime.engine.url.database is not None
        assert (tmp_path / "runtime_data" / "psit.db").is_file()
        assert runtime.formal_root == tmp_path / "runtime_data"
        assert runtime.importer.formal_root == runtime.formal_root
        assert runtime.query.formal_root == runtime.formal_root
        assert runtime.evidence.formal_root == runtime.formal_root.resolve()
    finally:
        runtime.engine.dispose()


def test_instance_lock_rejects_second_holder(tmp_path: Path) -> None:
    runtime_dir = tmp_path / "runtime_data"
    with instance_lock(runtime_dir):
        with pytest.raises(SingletonLockError):
            with instance_lock(runtime_dir):
                pass


def test_instance_lock_releases_after_context(tmp_path: Path) -> None:
    runtime_dir = tmp_path / "runtime_data"
    with instance_lock(runtime_dir):
        pass
    with instance_lock(runtime_dir):
        pass


def test_migration_failure_is_not_silently_ignored(tmp_path: Path, monkeypatch) -> None:
    from app.modules.application import wiring

    def fail(_engine):
        raise RuntimeError("migration failed")

    monkeypatch.setattr(wiring, "migrate_database", fail)
    with pytest.raises(RuntimeError, match="migration failed"):
        wiring.create_engine(tmp_path / "runtime_data")
