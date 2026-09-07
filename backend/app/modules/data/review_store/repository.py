"""M1-08：ReviewStore 写仓储（技术实施规格 11.1/12.3）。

所有方法接收调用方传入的 Session，由 ReviewStore 网关统一管理事务生命周期：
每个 ReviewStore 命令即一个短事务，定位、写入、校验在同一事务内完成，失败整体
回滚，成功一次性提交（规格 8：M3 不提交 Session，M1 负责完整写入）。

- review_id/submission_id 全局唯一、同一案例最多一份正式人工确认由数据库
  唯一约束最终保护（规格 11.1）；
- reviews 表只保存人工最终确认，系统原结果经 case_run_id 引用 stage_results，
  不在本表复制第二份决策包（规格第 8 节）；
- 本仓储只做追加/更新，不覆盖旧运行、旧阶段结果与旧模型调用（规格 11.2）。
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.contracts.states import CaseStatus
from app.modules.data.db.models import (
    Batch,
    BatchRun,
    Case,
    CaseRun,
    InterventionLevel,
    Review,
    ReviewOutcome,
    StageResult,
)


class ReviewStoreRepository:
    """ReviewStore 写仓储：命令事务由网关统一开启/提交/回滚。"""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    # ---------- 定位 ----------

    def batch_by_batch_id(self, session: Session, batch_id: str) -> Batch | None:
        """按全局唯一 batch_id 定位批次（规格 11.1）。"""
        return session.scalar(select(Batch).where(Batch.batch_id == batch_id))

    def batch_by_internal_id(
        self, session: Session, batch_internal_id: int
    ) -> Batch | None:
        """按内部主键定位批次。"""
        return session.get(Batch, batch_internal_id)

    def case_by_internal_id(self, session: Session, case_internal_id: int) -> Case | None:
        """按内部主键定位案例。"""
        return session.get(Case, case_internal_id)

    def case_of_batch(
        self, session: Session, batch_internal_id: int, case_id: str
    ) -> Case | None:
        """批次内唯一 (batch_id, case_id) 的案例（规格 11.1）。"""
        return session.scalar(
            select(Case).where(
                Case.batch_id == batch_internal_id, Case.case_id == case_id
            )
        )

    def case_run_by_id(
        self, session: Session, case_run_internal_id: int
    ) -> CaseRun | None:
        """按内部 case_run_id 定位案例运行（M3 ReviewSubmit 使用，规格 12.3）。"""
        return session.get(CaseRun, case_run_internal_id)

    def review_by_submission_id(
        self, session: Session, submission_id: str
    ) -> Review | None:
        """按全局唯一 submission_id 定位人工确认（幂等识别，规格 12.3）。"""
        return session.scalar(select(Review).where(Review.submission_id == submission_id))

    def review_of_case(self, session: Session, case_internal_id: int) -> Review | None:
        """案例正式人工确认（v1 每案例最多一份，规格 11.1 uq_reviews_case_id）。"""
        return session.scalar(select(Review).where(Review.case_id == case_internal_id))

    # ---------- 批量读取（批次投影重算用，规格 10.3） ----------

    def cases_of_batch(self, session: Session, batch_internal_id: int) -> list[Case]:
        """批次全部案例：imported_at/case_id 升序稳定基线。"""
        return list(
            session.scalars(
                select(Case)
                .where(Case.batch_id == batch_internal_id)
                .order_by(Case.imported_at.asc(), Case.case_id.asc())
            )
        )

    def runs_by_ids(
        self, session: Session, run_internal_ids: Iterable[int]
    ) -> dict[int, CaseRun]:
        """按内部 ID 批量取 case_run 行（当前投影定位用）。"""
        ids = {int(i) for i in run_internal_ids if i is not None}
        if not ids:
            return {}
        rows = list(session.scalars(select(CaseRun).where(CaseRun.id.in_(ids))))
        return {row.id: row for row in rows}

    def stage_result_names(
        self, session: Session, run_internal_ids: Iterable[int]
    ) -> dict[int, frozenset[str]]:
        """各 case_run 已保存的阶段名集合（完整决策包判断，规格 10.3/10.4）。"""
        ids = {int(i) for i in run_internal_ids if i is not None}
        if not ids:
            return {}
        rows = session.execute(
            select(StageResult.case_run_id, StageResult.stage_name).where(
                StageResult.case_run_id.in_(ids)
            )
        ).all()
        grouped: dict[int, set[str]] = {}
        for run_id, stage_name in rows:
            grouped.setdefault(run_id, set()).add(stage_name)
        return {run_id: frozenset(names) for run_id, names in grouped.items()}

    def stage_results_of_run(
        self, session: Session, case_run_internal_id: int
    ) -> list[StageResult]:
        """案例运行的阶段结果（插入顺序，供人工确认视图回填，规格第 8 节）。"""
        return list(
            session.scalars(
                select(StageResult)
                .where(StageResult.case_run_id == case_run_internal_id)
                .order_by(StageResult.created_at.asc(), StageResult.id.asc())
            )
        )

    def batch_runs_of_batch(
        self, session: Session, batch_internal_id: int
    ) -> list[BatchRun]:
        """批次首次批量分析历史（规格 10.3：batch_runs 只保存首次统计）。"""
        return list(
            session.scalars(
                select(BatchRun).where(BatchRun.batch_id == batch_internal_id)
            )
        )

    # ---------- 写入（由网关在同一事务内调用） ----------

    def insert_review(
        self,
        session: Session,
        *,
        review_id: str,
        submission_id: str,
        case_internal_id: int,
        case_run_internal_id: int,
        outcome: ReviewOutcome,
        final_intervention_level: InterventionLevel | None,
        final_cause_json: dict[str, Any] | None,
        final_actions_json: list[Any] | None,
        review_reason: str | None,
        execution_note: str | None,
        now: datetime,
    ) -> Review:
        """追加一份正式人工确认（review_id/submission_id/case_id 唯一约束保护）。"""
        row = Review(
            review_id=review_id,
            submission_id=submission_id,
            case_id=case_internal_id,
            case_run_id=case_run_internal_id,
            outcome=outcome,
            final_intervention_level=final_intervention_level,
            final_cause_json=final_cause_json,
            final_actions_json=final_actions_json,
            review_reason=review_reason,
            execution_note=execution_note,
            created_at=now,
        )
        session.add(row)
        session.flush()
        return row

    def update_case_review(
        self,
        session: Session,
        *,
        case_internal_id: int,
        review_internal_id: int,
        status: CaseStatus,
        final_intervention_level: InterventionLevel | None,
        now: datetime,
    ) -> None:
        """同事务更新案例人工确认指针/状态；final 等级仅人工提供时写入。"""
        row = self.case_by_internal_id(session, case_internal_id)
        if row is None:
            return
        row.current_review_id = review_internal_id
        row.status = status
        if final_intervention_level is not None:
            row.final_intervention_level = final_intervention_level
        row.updated_at = now

    def update_batch_projection(
        self,
        session: Session,
        *,
        batch_internal_id: int,
        status,
        analysis_succeeded_count: int,
        error_count: int,
        now: datetime,
    ) -> None:
        """同事务更新 batches 当前状态与三项计数（规格 10.3/10.4）。"""
        row = self.batch_by_internal_id(session, batch_internal_id)
        if row is None:
            return
        row.status = status
        row.analysis_succeeded_count = analysis_succeeded_count
        row.error_count = error_count
        row.updated_at = now


__all__ = ["ReviewStoreRepository"]
