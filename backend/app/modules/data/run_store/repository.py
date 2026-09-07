"""M1-07：RunStore 写仓储（技术实施规格 10.2—10.5/11.1—11.2）。

所有方法接收调用方传入的 Session，由 RunStore 网关统一管理事务生命周期：
每个 RunStore 命令即一个短事务，定位、写入、校验在同一事务内完成，失败整体
回滚，成功一次性提交（规格 8：M3 不提交 Session，M1 负责完整写入）。

- run_id/call_id 全局唯一、case_run+stage_name 唯一由数据库约束最终保护；
- 同一案例最多一个活动 case_run、全系统最多一个活动 batch_run 由 SQLite
  部分唯一索引强制（规格 10.1：数据库唯一约束是最终保护）；
- 本仓储只做追加/更新，不覆盖旧运行、旧阶段结果与旧模型调用（规格 11.2）。
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.contracts.states import BatchRunStatus, CaseRunStatus
from app.modules.data.db.models import (
    Batch,
    BatchRun,
    Case,
    CaseRun,
    ModelCall,
    StageResult,
)

from .types import ModelAttemptInput

_BATCH_RUN_ACTIVE = (BatchRunStatus.STARTING, BatchRunStatus.RUNNING)
_CASE_RUN_ACTIVE = (
    CaseRunStatus.STARTING,
    CaseRunStatus.PERCEPTION_RUNNING,
    CaseRunStatus.ATTRIBUTION_RUNNING,
    CaseRunStatus.STRATEGY_RUNNING,
)


class RunStoreRepository:
    """RunStore 写仓储：命令事务由网关统一开启/提交/回滚。"""

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

    def batch_run_by_run_id(self, session: Session, run_id: str) -> BatchRun | None:
        """按全局唯一 run_id 定位批次运行（幂等创建识别）。"""
        return session.scalar(select(BatchRun).where(BatchRun.run_id == run_id))

    def batch_run_by_id(
        self, session: Session, batch_run_internal_id: int
    ) -> BatchRun | None:
        """按内部主键定位批次运行。"""
        return session.get(BatchRun, batch_run_internal_id)

    def case_run_by_run_id(self, session: Session, run_id: str) -> CaseRun | None:
        """按全局唯一 run_id 定位案例运行（幂等创建识别）。"""
        return session.scalar(select(CaseRun).where(CaseRun.run_id == run_id))

    def case_run_by_id(
        self, session: Session, case_run_internal_id: int
    ) -> CaseRun | None:
        """按内部 case_run_id 定位案例运行（M3 AnalysisRequest 使用，规格 9.1）。"""
        return session.get(CaseRun, case_run_internal_id)

    def model_call_by_call_id(self, session: Session, call_id: str) -> ModelCall | None:
        """按全局唯一 call_id 定位模型调用（幂等追加识别）。"""
        return session.scalar(select(ModelCall).where(ModelCall.call_id == call_id))

    def stage_result_of_run(
        self, session: Session, case_run_id: int, stage_name: str
    ) -> StageResult | None:
        """同一 case_run+stage_name 的唯一阶段结果（规格 11.1）。"""
        return session.scalar(
            select(StageResult).where(
                StageResult.case_run_id == case_run_id,
                StageResult.stage_name == stage_name,
            )
        )

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

    def batch_runs_of_batch(
        self, session: Session, batch_internal_id: int
    ) -> list[BatchRun]:
        """批次首次批量分析历史（规格 10.3：batch_runs 只保存首次统计）。"""
        return list(
            session.scalars(
                select(BatchRun).where(BatchRun.batch_id == batch_internal_id)
            )
        )

    def batch_runs_history(
        self, session: Session, batch_internal_id: int
    ) -> list[BatchRun]:
        """按 started_at 升序返回批次首次运行历史（供"首次历史"只读投影）。"""
        return list(
            session.scalars(
                select(BatchRun)
                .where(BatchRun.batch_id == batch_internal_id)
                .order_by(BatchRun.started_at.asc())
            )
        )

    def case_runs_history(
        self, session: Session, case_internal_id: int
    ) -> list[CaseRun]:
        """按 created_at 升序返回案例全部运行历史（只追加不覆盖，规格 11.2）。"""
        return list(
            session.scalars(
                select(CaseRun)
                .where(CaseRun.case_id == case_internal_id)
                .order_by(CaseRun.created_at.asc())
            )
        )

    def active_case_runs(self, session: Session) -> list[CaseRun]:
        """全系统活动（STARTING/…/STRATEGY_RUNNING）案例运行（启动恢复用）。"""
        return list(
            session.scalars(select(CaseRun).where(CaseRun.status.in_(_CASE_RUN_ACTIVE)))
        )

    def active_batch_runs(self, session: Session) -> list[BatchRun]:
        """全系统活动（STARTING/RUNNING）批次运行（启动恢复用）。"""
        return list(
            session.scalars(select(BatchRun).where(BatchRun.status.in_(_BATCH_RUN_ACTIVE)))
        )

    def active_batch_run_exists(self, session: Session) -> bool:
        """是否存在活动批次运行（can_start_analysis 与创建冲突提示用，规格 10.1）。"""
        return bool(self.active_batch_runs(session))

    # ---------- 追加写入（由网关在同一事务内调用） ----------

    def insert_batch_run(
        self,
        session: Session,
        *,
        run_id: str,
        batch_internal_id: int,
        status: BatchRunStatus,
        total_case_count: int,
        started_at: datetime,
        now: datetime,
    ) -> BatchRun:
        """追加一条首次批次运行（STARTING）；run_id 唯一约束由数据库保护。"""
        row = BatchRun(
            run_id=run_id,
            batch_id=batch_internal_id,
            status=status,
            total_case_count=total_case_count,
            analysis_succeeded_count=0,
            error_count=0,
            started_at=started_at,
            finished_at=None,
            updated_at=now,
        )
        session.add(row)
        session.flush()
        return row

    def insert_case_run(
        self,
        session: Session,
        *,
        run_id: str,
        case_internal_id: int,
        batch_run_internal_id: int | None,
        previous_case_run_id: int | None,
        trigger_type,
        status: CaseRunStatus,
        current_stage: str | None,
        started_at: datetime,
        now: datetime,
    ) -> CaseRun:
        """追加一条案例运行；同案例活动唯一由 SQLite 部分唯一索引强制。"""
        row = CaseRun(
            run_id=run_id,
            case_id=case_internal_id,
            batch_run_id=batch_run_internal_id,
            previous_case_run_id=previous_case_run_id,
            trigger_type=trigger_type,
            status=status,
            current_stage=current_stage,
            error_code=None,
            error_stage=None,
            error_detail_json=None,
            started_at=started_at,
            finished_at=None,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        session.flush()
        return row

    def insert_model_call(
        self, session: Session, *, case_run_id: int, attempt: ModelAttemptInput, now: datetime
    ) -> ModelCall:
        """追加一条模型调用记录（call_id 全局唯一，只追加不覆盖，规格 9.2/11.2）。"""
        started_at = attempt.started_at if attempt.started_at is not None else now
        finished_at = attempt.finished_at if attempt.finished_at is not None else now
        row = ModelCall(
            call_id=attempt.call_id,
            case_run_id=case_run_id,
            stage_name=attempt.stage_name,
            attempt_no=attempt.attempt_no,
            model_name=attempt.model_name,
            prompt_version=attempt.prompt_version,
            request_manifest_json=attempt.request_manifest_json,
            status=attempt.status,
            response_json=attempt.response_json,
            error_json=attempt.error_json,
            started_at=started_at,
            finished_at=finished_at,
            latency_ms=attempt.latency_ms,
            prompt_token_count=attempt.prompt_token_count,
            completion_token_count=attempt.completion_token_count,
            total_token_count=attempt.total_token_count,
        )
        session.add(row)
        return row

    def insert_stage_result(
        self,
        session: Session,
        *,
        case_run_id: int,
        stage_name: str,
        contract_version: str,
        result_json: object,
        result_sha256: str,
        now: datetime,
    ) -> StageResult:
        """追加一份阶段最终合格结果（case_run+stage_name 唯一，规格 11.1）。"""
        row = StageResult(
            case_run_id=case_run_id,
            stage_name=stage_name,
            contract_version=contract_version,
            result_json=result_json,
            result_sha256=result_sha256,
            created_at=now,
        )
        session.add(row)
        session.flush()
        return row

    # ---------- 计数与投影更新（同一事务） ----------

    def increment_batch_run_success(
        self, session: Session, batch_run_internal_id: int, now: datetime
    ) -> None:
        """首次批量运行的成功案例计数 +1（规格 10.3 历史统计）。"""
        row = self.batch_run_by_id(session, batch_run_internal_id)
        if row is not None and row.status in _BATCH_RUN_ACTIVE:
            row.analysis_succeeded_count += 1
            row.updated_at = now

    def increment_batch_run_error(
        self, session: Session, batch_run_internal_id: int, now: datetime
    ) -> None:
        """首次批量运行的异常案例计数 +1（规格 10.3 历史统计）。"""
        row = self.batch_run_by_id(session, batch_run_internal_id)
        if row is not None and row.status in _BATCH_RUN_ACTIVE:
            row.error_count += 1
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


__all__ = ["RunStoreRepository"]
