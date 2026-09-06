"""M1-05：查询投影仓储（技术实施规格 8/10.3/11.2/12.2；ADR-0036/0079）。

为 CaseQueryGateway 提供只读访问：批次分页、案例、运行历史、阶段结果、
人工确认、证据计数与正式目录包文件名。每次方法调用使用独立同步短 Session
（规格 11.2），不跨会话持有 ORM 对象；source_filename 从正式目录已保存的
source_filename.txt 读取（规格 12.2），网关不自行生成业务数据。

批量状态与三项计数由网关从 cases + 当前 case_run 实时聚合（规格 10.3），
本仓储只提供聚合所需的原始行与计数。
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path, PurePosixPath

from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.contracts.states import BatchRunStatus, CaseRunStatus
from app.modules.data.db.models import (
    Batch,
    BatchRun,
    Case,
    CaseRun,
    Evidence,
    Review,
    StageResult,
)

_BATCH_RUN_ACTIVE = (BatchRunStatus.STARTING, BatchRunStatus.RUNNING)
_CASE_RUN_ACTIVE = (
    CaseRunStatus.STARTING,
    CaseRunStatus.PERCEPTION_RUNNING,
    CaseRunStatus.ATTRIBUTION_RUNNING,
    CaseRunStatus.STRATEGY_RUNNING,
)


class CaseQueryRepository:
    """M1 查询投影只读仓储：独立短 Session、稳定排序、无 ORM/内部 ID 泄漏。"""

    def __init__(self, engine: Engine, *, formal_root: Path) -> None:
        self._engine = engine
        self.formal_root = Path(formal_root)

    # ---------- 批次 ----------

    def list_batches(self, *, limit: int, offset: int) -> tuple[list[Batch], int]:
        """批次分页：imported_at 倒序、batch_id 升序稳定排序（规格 12.1）。"""
        with Session(self._engine) as session:
            total = int(session.scalar(select(func.count(Batch.id))) or 0)
            rows = list(
                session.scalars(
                    select(Batch)
                    .order_by(Batch.imported_at.desc(), Batch.batch_id.asc())
                    .limit(limit)
                    .offset(offset)
                )
            )
            return rows, total

    def batch_by_batch_id(self, batch_id: str) -> Batch | None:
        """按全局唯一 batch_id 查询批次（规格 5.4/12.1）。"""
        with Session(self._engine) as session:
            return session.scalar(select(Batch).where(Batch.batch_id == batch_id))

    def source_filename(self, batch: Batch) -> str:
        """正式目录 source_filename.txt 已保存包文件名（规格 12.2）。"""
        rel = PurePosixPath(batch.package_relative_path).parts
        formal_dir = self.formal_root.joinpath(*rel) if rel else self.formal_root
        try:
            return (
                formal_dir / "source_filename.txt"
            ).read_text(encoding="utf-8").strip()
        except (OSError, UnicodeDecodeError):
            return ""

    def batch_runs_of_batch(self, batch_internal_id: int) -> list[BatchRun]:
        """批次首次批量分析历史（规格 10.3：batch_runs 只保存首次统计）。"""
        with Session(self._engine) as session:
            return list(
                session.scalars(
                    select(BatchRun).where(BatchRun.batch_id == batch_internal_id)
                )
            )

    def active_batch_run_exists(self) -> bool:
        """全系统是否存在活动（STARTING/RUNNING）首次批次运行（规格 10.1/10.3）。"""
        with Session(self._engine) as session:
            count = session.scalar(
                select(func.count(BatchRun.id)).where(
                    BatchRun.status.in_(_BATCH_RUN_ACTIVE)
                )
            )
            return int(count or 0) > 0

    # ---------- 案例 ----------

    def cases_of_batch(self, batch_internal_id: int) -> list[Case]:
        """批次全部案例，按 imported_at/case_id 升序返回（稳定基线）。"""
        with Session(self._engine) as session:
            return list(
                session.scalars(
                    select(Case)
                    .where(Case.batch_id == batch_internal_id)
                    .order_by(Case.imported_at.asc(), Case.case_id.asc())
                )
            )

    def case_of_batch(self, batch_internal_id: int, case_id: str) -> Case | None:
        """批次内唯一（batch_id, case_id）的案例（规格 11.1）。"""
        with Session(self._engine) as session:
            return session.scalar(
                select(Case).where(
                    Case.batch_id == batch_internal_id, Case.case_id == case_id
                )
            )

    # ---------- 运行 / 阶段结果 / 人工确认 ----------

    def runs_by_ids(self, run_internal_ids: Iterable[int]) -> dict[int, CaseRun]:
        """按内部 ID 批量取 case_run 行（当前投影定位用）。"""
        ids = {int(i) for i in run_internal_ids if i is not None}
        if not ids:
            return {}
        with Session(self._engine) as session:
            rows = list(
                session.scalars(select(CaseRun).where(CaseRun.id.in_(ids)))
            )
            return {row.id: row for row in rows}

    def case_runs_of_case(self, case_internal_id: int) -> list[CaseRun]:
        """案例全部运行历史（created_at 升序；首个 BATCH 运行用于首次历史）。"""
        with Session(self._engine) as session:
            return list(
                session.scalars(
                    select(CaseRun)
                    .where(CaseRun.case_id == case_internal_id)
                    .order_by(CaseRun.created_at.asc())
                )
            )

    def active_case_run_of_case(self, case_internal_id: int) -> CaseRun | None:
        """同一案例的活动（STARTING/…/STRATEGY_RUNNING）case_run（规格 10.1）。"""
        with Session(self._engine) as session:
            return session.scalar(
                select(CaseRun).where(
                    CaseRun.case_id == case_internal_id,
                    CaseRun.status.in_(_CASE_RUN_ACTIVE),
                )
            )

    def stage_result_counts(
        self, run_internal_ids: Iterable[int]
    ) -> dict[int, int]:
        """各 case_run 的阶段结果条数（完整决策包判断；规格 10.3/10.4）。"""
        ids = {int(i) for i in run_internal_ids if i is not None}
        if not ids:
            return {}
        with Session(self._engine) as session:
            rows = session.execute(
                select(StageResult.case_run_id, func.count(StageResult.id))
                .where(StageResult.case_run_id.in_(ids))
                .group_by(StageResult.case_run_id)
            ).all()
            return {run_id: int(count) for run_id, count in rows}

    def stage_results_of_runs(
        self, run_internal_ids: Iterable[int]
    ) -> dict[int, list[StageResult]]:
        """批量取各 case_run 的阶段结果（按插入顺序；同一 run+stage 唯一）。"""
        ids = {int(i) for i in run_internal_ids if i is not None}
        if not ids:
            return {}
        with Session(self._engine) as session:
            rows = list(
                session.scalars(
                    select(StageResult)
                    .where(StageResult.case_run_id.in_(ids))
                    .order_by(StageResult.id.asc())
                )
            )
        grouped: dict[int, list[StageResult]] = {}
        for row in rows:
            grouped.setdefault(row.case_run_id, []).append(row)
        return grouped

    def reviews_of_case(self, case_internal_id: int) -> list[Review]:
        """案例正式人工确认结果（v1 每案例最多一份，按创建时间升序）。"""
        with Session(self._engine) as session:
            return list(
                session.scalars(
                    select(Review)
                    .where(Review.case_id == case_internal_id)
                    .order_by(Review.created_at.asc())
                )
            )

    # ---------- 证据 ----------

    def evidence_count_for_batch(self, batch_internal_id: int) -> int:
        """给定批次内部 ID 的 evidence 行数（规格 12.2：evidence_count 表计数）。"""
        with Session(self._engine) as session:
            count = session.scalar(
                select(func.count(Evidence.id))
                .join(Case, Evidence.case_id == Case.id)
                .where(Case.batch_id == batch_internal_id)
            )
            return int(count or 0)

    def evidence_of_case(self, case_internal_id: int) -> list[Evidence]:
        """案例全部证据行（顺序按插入顺序，供 cited_evidence 映射）。"""
        with Session(self._engine) as session:
            return list(
                session.scalars(
                    select(Evidence).where(Evidence.case_id == case_internal_id)
                )
            )
