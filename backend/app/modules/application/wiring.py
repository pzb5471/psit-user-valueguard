"""M3-08 真实 M1 装配与运行环境（技术实施规格 8、10、14；ADR 0033、0084）。

把 Fake M1 替换为真实 SQLite 端口，并在启动生命周期内完成迁移、单实例锁与
启动恢复。M3 只在这里把 M1 的公开端口注入各 M3 服务；不操作 ORM、不改 M1
内部实现。运行数据锚定到 settings 解析的项目根 runtime_dir（ADR 0082）。
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from sqlite3 import Connection as SQLiteConnection

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine as sqlalchemy_create_engine
from sqlalchemy import event
from sqlalchemy.engine import Engine

from app.modules.application.review.service import ReviewService
from app.modules.application.run_service.ports import AnalysisEnginePort
from app.modules.application.run_service.service import RunService
from app.modules.application.run_service.versions import AnalysisVersionConfig
from app.modules.application.services.query import ApplicationServices, M1Ports
from app.modules.data.evidence.gateway import EvidenceGateway
from app.modules.data.importing.gateway import BatchImportGateway
from app.modules.data.importing.zip_stage import DEFAULT_MAX_ZIP_BYTES
from app.modules.data.queries.gateway import CaseQueryGateway
from app.modules.data.review_store.gateway import ReviewStore
from app.modules.data.run_store.gateway import RunStore

BACKEND_ALEMBIC = Path(__file__).resolve().parents[3] / "alembic" / "alembic.ini"


class SingletonLockError(RuntimeError):
    """运行目录已被另一实例占用（规格 10.5 单实例锁；ADR 0084）。"""


def _enable_foreign_keys(dbapi_connection: SQLiteConnection, _record: object) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def migrate_database(engine: Engine) -> None:
    """对 engine 对应库执行 alembic upgrade head（PSIT_DB_URL 指向该库）。"""
    cfg = Config(str(BACKEND_ALEMBIC))
    previous = os.environ.get("PSIT_DB_URL")
    os.environ["PSIT_DB_URL"] = engine.url.render_as_string(hide_password=False)
    try:
        command.upgrade(cfg, "head")
    finally:
        if previous is None:
            os.environ.pop("PSIT_DB_URL", None)
        else:
            os.environ["PSIT_DB_URL"] = previous


def create_engine(runtime_dir: Path) -> Engine:
    """创建已迁移的 SQLite 引擎（外键开启，规格 11.2）。"""
    runtime_dir.mkdir(parents=True, exist_ok=True)
    db_path = runtime_dir / "psit.db"
    engine = sqlalchemy_create_engine(f"sqlite:///{db_path.as_posix()}")
    event.listen(engine, "connect", _enable_foreign_keys)
    migrate_database(engine)
    return engine


@contextmanager
def instance_lock(runtime_dir: Path) -> Iterator[None]:
    """Windows 排它运行目录锁：第二个实例立即失败（规格 10.5；ADR 0084）。"""
    runtime_dir.mkdir(parents=True, exist_ok=True)
    lock_path = runtime_dir / ".instance.lock"
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT)
    try:
        try:
            if os.fstat(fd).st_size == 0:
                os.write(fd, b"\x00")
        except PermissionError:
            # 另一个进程可能已持有文件共享锁；继续到排他锁检测。
            pass
        os.lseek(fd, 0, os.SEEK_SET)
        import msvcrt

        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise SingletonLockError(
                f"运行目录已被另一实例锁定：{runtime_dir}"
            ) from exc
        try:
            yield
        finally:
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    finally:
        os.close(fd)


@dataclass(frozen=True, slots=True)
class RealRuntime:
    """真实 M1 各端口与共享对象；M3 各服务从它装配。"""

    runtime_dir: Path
    engine: Engine
    formal_root: Path
    importer: BatchImportGateway
    query: CaseQueryGateway
    evidence: EvidenceGateway
    run_store: RunStore
    review_store: ReviewStore


def build_runtime(runtime_dir: Path) -> RealRuntime:
    """创建 engine、迁移并把真实 M1 端口接线到运行时对象。"""
    engine = create_engine(runtime_dir)
    formal_root = runtime_dir
    return RealRuntime(
        runtime_dir=runtime_dir,
        engine=engine,
        formal_root=formal_root,
        importer=BatchImportGateway(
            engine=engine, formal_root=formal_root, max_zip_bytes=DEFAULT_MAX_ZIP_BYTES
        ),
        query=CaseQueryGateway(engine=engine, formal_root=formal_root),
        evidence=EvidenceGateway(engine=engine, formal_root=formal_root),
        run_store=RunStore(engine=engine),
        review_store=ReviewStore(engine=engine),
    )


class M1RunQueryGateway:
    """包装 M1 CaseQueryGateway 并提供 M3 运行编排所需的内部运行查询。

    get_current_case_run_id：通过 RunStore.case_run_history 取该案例最新运行的
    内部 id（重跑后 history 最新即当前；M3 不碰 ORM）。若 M1 后续提供公开的
    当前运行查询，可替换本适配。
    """

    def __init__(self, query: CaseQueryGateway, run_store: RunStore) -> None:
        self._query = query
        self._run_store = run_store

    def get_batch(self, batch_id: str):
        return self._query.get_batch(batch_id)

    def list_cases(self, batch_id: str, *, limit=None, offset=None):
        return self._query.list_cases(batch_id, limit=limit, offset=offset)

    def get_case_detail(self, batch_id: str, case_id: str):
        return self._query.get_case_detail(batch_id, case_id)

    def get_case_input(self, batch_id: str, case_id: str):
        return self._query.get_case_input(batch_id, case_id)

    def get_current_case_run_id(self, batch_id: str, case_id: str) -> int | None:
        history = self._run_store.case_run_history(batch_id, case_id)
        if not history:
            return None
        return history[-1].id


def build_versions() -> AnalysisVersionConfig:
    """M3-08 固定版本；M3-09 接真实 M2 时由 M2 提供实际值。"""
    return AnalysisVersionConfig(
        perception_contract_version="v1",
        attribution_contract_version="v1",
        strategy_contract_version="v1",
        perception_prompt_version="v1",
        attribution_prompt_version="v1",
        strategy_prompt_version="v1",
        action_catalog_version="v1",
    )

@dataclass(frozen=True, slots=True)
class RealServices:
    """真实 M1 端口装配后的三个 M3 服务。"""

    application: ApplicationServices
    run: RunService
    review: ReviewService


def build_services(
    runtime: RealRuntime,
    *,
    analysis_engine: AnalysisEnginePort,
    versions: AnalysisVersionConfig | None = None,
    max_concurrency: int = 2,
    analysis_available: bool = True,
    analysis_unavailable_message: str | None = None,
) -> RealServices:
    """将真实 M1 端口接入 M3；M2 引擎由 M3-09 注入。"""
    query = M1RunQueryGateway(runtime.query, runtime.run_store)
    application = ApplicationServices(
        M1Ports(
            importer=runtime.importer,
            query=runtime.query,
            evidence=runtime.evidence,
        ),
        analysis_available=analysis_available,
        analysis_unavailable_message=analysis_unavailable_message,
    )
    run = RunService(
        run_store=runtime.run_store,
        analysis_engine=analysis_engine,
        query=query,
        versions=versions or build_versions(),
        max_concurrency=max_concurrency,
        analysis_available=analysis_available,
        analysis_unavailable_message=analysis_unavailable_message,
    )
    review = ReviewService(query=query, review_store=runtime.review_store)
    return RealServices(application=application, run=run, review=review)
