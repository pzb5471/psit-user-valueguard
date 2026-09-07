"""M1-07：RunStore（技术实施规格 8/9.2/10.1—10.5/11.1—11.2）。

RunStore 对 M3 提供一组“短事务命令”：每个命令在独立同步 Session 中打开一次
事务、完成全部写入后提交；M3 不接触 Session、不自行提交（规格第 8 节）。
命令只写入 M3 决定的状态转换结果，本网关不自行裁决案例状态迁移（规格 10.2）：

- create_batch_run：幂等创建首次批次运行（STARTING）并切换
  batches.current_batch_run_id（M3 决定开始批次，批次投影按 10.3 推导）；
- create_case_run：幂等创建案例运行并切换 cases.current_case_run_id，
  previous_case_run_id 自动取被替换的当前运行（旧运行只保留不覆盖）；
- record_stage_started / record_model_attempt / record_stage_result：阶段事件
  追加（current_stage 更新、model_calls/stage_results 只追加，不覆盖旧历史）；
- record_failure：记录技术失败（case_run FAILED + 错误字段、案例
  PROCESSING_ERROR）并同事务重算批次当前状态与三项计数、首次批量运行计数；
- publish_complete_result：完整决策包原子发布（规格 10.4）——最终阶段结果、
  case_run 成功状态、cases.current_case_run_id、案例 PENDING_REVIEW 与批次
  当前状态/计数在同一事务提交；缺任一阶段结果抛
  IncompleteDecisionPackageError，整个事务回滚（不发布半个决策包）；
- finish_batch_run：M3 判定首次批量分析结束后关闭当前 batch_run（历史统计冻结）；
- recover_interrupted：启动恢复原语（规格 10.5）——幂等标记活动运行
  INTERRUPTED、未完整发布案例进入 PROCESSING_ERROR(APP_INTERRUPTED)、活动批次
  运行 INTERRUPTED、保留全部历史并重算受影响批次投影。

批次当前状态与三项计数按规格 10.3 由当前案例推导（与 CaseQueryGateway 同源
公式）；batch_runs 只保存首次批量分析历史统计，MANUAL_RERUN（batch_run_id 为
空）不创建伪批次运行、不修改已结束的 batch_runs（规格 10.3 禁止事项）。该推导
是规格 10.3 的确定性公式，不属于 M1 自行发明状态转换；案例级转换一律由命令
参数显式传入（M3 裁决）。

显式假设（超出规格字面处在此声明，供 M2-01/M3-03 与人工 PR 复审）：
- 完整决策包的三个阶段名冻结为 ("perception", "attribution", "strategy")，
  与 M1-05 内部阶段名和 _ERROR_BUSINESS_STAGE 对齐；M2-01 冻结结果合同后如有
  官方阶段名在此对齐；
- publish 的 system_intervention_level 由 M3 从决策包显式传入（本网关不解释
  结果 JSON）；不传入则保持 cases.system_intervention_level 原值；
- 阶段事件不落独立事件表（九表 Schema 无 events 表，规格 11.1），而是追加到
  model_calls/stage_results 并更新 case_run.current_stage；事件持久化失败时
  异常向上抛给 M3，M3 立即停止当前案例（规格 9.1）；
- 发布/失败命令具备幂等重入（重复调用返回已生效结果，不重复计数）：发布以
  case_run SUCCEEDED + 案例 PENDING_REVIEW/COMPLETED + 完整包为幂等键；
- recover_interrupted 把未完整发布的运行错误记为 APP_INTERRUPTED + 内部阶段
  app_recovery（M1-05 已映射为 APP_RECOVERY 业务阶段），并保留 current_stage
  供诊断；
- 案例级转换合法性（如 COMPLETED 禁止重跑）由 M3 在编排层裁决，本网关只执行
  机械不变式：活动唯一（数据库约束）、不发布半个决策包、不覆盖旧运行。
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.contracts.states import (
    BatchRunStatus,
    BatchStatus,
    CaseRunStatus,
    CaseStatus,
    TriggerType,
)

from ..db.models import Batch, BatchRun, Case, CaseRun, InterventionLevel
from .errors import (
    ActiveRunConflictError,
    IncompleteDecisionPackageError,
    RunNotActiveError,
    RunStoreResourceNotFoundError,
    StageResultConflictError,
)
from .repository import RunStoreRepository
from .types import (
    BatchRunView,
    CaseRunView,
    FailureResult,
    ModelAttemptInput,
    PublishResult,
    RecoverySummary,
    StageResultInput,
)

#: 完整决策包的三个阶段名（规格 9/10.4；M2-01 冻结后对齐官方阶段名）。
COMPLETE_PACKAGE_STAGES: tuple[str, ...] = ("perception", "attribution", "strategy")
_COMPLETE_PACKAGE_SET = frozenset(COMPLETE_PACKAGE_STAGES)

_ACTIVE_CASE_RUN_STATUSES = (
    CaseRunStatus.STARTING,
    CaseRunStatus.PERCEPTION_RUNNING,
    CaseRunStatus.ATTRIBUTION_RUNNING,
    CaseRunStatus.STRATEGY_RUNNING,
)
_TERMINAL_BATCH_RUN_STATUSES = (
    BatchRunStatus.COMPLETED,
    BatchRunStatus.COMPLETED_WITH_ERRORS,
    BatchRunStatus.FAILED,
    BatchRunStatus.INTERRUPTED,
)

#: 启动恢复错误（规格 10.5 #2）与内部阶段（M1-05 已映射为 APP_RECOVERY）。
APP_INTERRUPTED_CODE = "APP_INTERRUPTED"
APP_RECOVERY_STAGE = "app_recovery"


def _now(value: datetime | None) -> datetime:
    """命令时间戳：未显式传入时取当前 UTC（规格 11.2：UTC 毫秒时间）。"""
    return value if value is not None else datetime.now(UTC)


def _has_complete_package(
    case: Case, runs: dict[int, CaseRun], names: dict[int, frozenset[str]]
) -> bool:
    """完整决策包：当前 case_run 且三阶段结果齐备（规格 10.3/10.4）。"""
    if case.current_case_run_id is None or case.current_case_run_id not in runs:
        return False
    return _COMPLETE_PACKAGE_SET.issubset(
        names.get(case.current_case_run_id, frozenset())
    )


def _batch_status(
    cases: list[Case],
    runs: dict[int, CaseRun],
    names: dict[int, frozenset[str]],
    has_batch_runs: bool,
) -> BatchStatus:
    """批次状态由当前案例推导（规格 10.3；与 CaseQueryGateway 同源公式）。"""
    statuses = [case.status for case in cases]
    if any(status == CaseStatus.ANALYZING for status in statuses):
        return BatchStatus.ANALYZING
    if any(status == CaseStatus.PROCESSING_ERROR for status in statuses):
        return BatchStatus.COMPLETED_WITH_ERRORS
    if all(status == CaseStatus.PENDING_ANALYSIS for status in statuses) and not has_batch_runs:
        return BatchStatus.PENDING_ANALYSIS
    if all(
        status in (CaseStatus.PENDING_REVIEW, CaseStatus.COMPLETED) for status in statuses
    ) and all(_has_complete_package(case, runs, names) for case in cases):
        return BatchStatus.COMPLETED
    return BatchStatus.ANALYZING


class RunStore:
    """SQLite 版 RunStore：短事务命令保存运行、事件、失败与完整结果发布。"""

    def __init__(self, *, engine: Engine) -> None:
        self._engine = engine
        self.repository = RunStoreRepository(engine)

    @contextmanager
    def _transaction(self) -> Iterator[Session]:
        """一次短事务：独立同步 Session，成功提交、失败整体回滚（规格 11.2）。"""
        session = Session(self._engine)
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ---------- 视图构造 ----------

    @staticmethod
    def _batch_run_view(row: BatchRun, batch_id: str) -> BatchRunView:
        return BatchRunView(
            id=row.id,
            run_id=row.run_id,
            batch_id=batch_id,
            status=row.status.value,
            total_case_count=row.total_case_count,
            analysis_succeeded_count=row.analysis_succeeded_count,
            error_count=row.error_count,
            started_at=row.started_at.isoformat(),
            finished_at=row.finished_at.isoformat() if row.finished_at is not None else None,
        )

    @staticmethod
    def _case_run_view(row: CaseRun, batch_id: str, case_id: str) -> CaseRunView:
        return CaseRunView(
            id=row.id,
            run_id=row.run_id,
            batch_id=batch_id,
            case_id=case_id,
            trigger_type=row.trigger_type.value,
            status=row.status.value,
            current_stage=row.current_stage,
            previous_case_run_id=row.previous_case_run_id,
            batch_run_id=row.batch_run_id,
            started_at=row.started_at.isoformat(),
            finished_at=row.finished_at.isoformat() if row.finished_at is not None else None,
        )

    # ---------- 定位与校验 ----------

    def _require_active_case_run(self, session: Session, case_run_id: int) -> CaseRun:
        """返回活动 case_run；不存在抛 404，已结束抛 RUN_NOT_ACTIVE。"""
        run = self.repository.case_run_by_id(session, case_run_id)
        if run is None:
            raise RunStoreResourceNotFoundError(
                object_type="case_run", object_id=str(case_run_id)
            )
        if run.status not in _ACTIVE_CASE_RUN_STATUSES:
            raise RunNotActiveError(object_id=run.run_id)
        return run

    def _existing_batch_run_view(
        self, run_id: str, fallback_batch_id: str
    ) -> BatchRunView | None:
        """并发重入时按 run_id 读回已创建的批次运行（幂等返回）。"""
        with Session(self._engine) as session:
            row = self.repository.batch_run_by_run_id(session, run_id)
            if row is None:
                return None
            batch = self.repository.batch_by_internal_id(session, row.batch_id)
            return self._batch_run_view(
                row, batch.batch_id if batch is not None else fallback_batch_id
            )

    def _existing_case_run_view(
        self, run_id: str, fallback_batch_id: str, fallback_case_id: str
    ) -> CaseRunView | None:
        """并发重入时按 run_id 读回已创建的案例运行（幂等返回）。"""
        with Session(self._engine) as session:
            row = self.repository.case_run_by_run_id(session, run_id)
            if row is None:
                return None
            case = self.repository.case_by_internal_id(session, row.case_id)
            batch = (
                self.repository.batch_by_internal_id(session, case.batch_id)
                if case is not None
                else None
            )
            return self._case_run_view(
                row,
                batch.batch_id if batch is not None else fallback_batch_id,
                case.case_id if case is not None else fallback_case_id,
            )

    # ---------- 幂等创建运行与当前指针切换 ----------

    def create_batch_run(
        self,
        *,
        batch_id: str,
        run_id: str,
        total_case_count: int,
        batch_status: BatchStatus = BatchStatus.ANALYZING,
        started_at: datetime | None = None,
    ) -> BatchRunView:
        """幂等创建首次批次运行并切换 batches.current_batch_run_id（规格 10.3/11.1）。"""
        now = _now(started_at)
        try:
            with self._transaction() as session:
                existing = self.repository.batch_run_by_run_id(session, run_id)
                if existing is not None:
                    batch = self.repository.batch_by_internal_id(session, existing.batch_id)
                    return self._batch_run_view(
                        existing,
                        batch.batch_id if batch is not None else batch_id,
                    )
                batch = self.repository.batch_by_batch_id(session, batch_id)
                if batch is None:
                    raise RunStoreResourceNotFoundError(
                        object_type="batch", object_id=batch_id
                    )
                if self.repository.active_batch_run_exists(session):
                    raise ActiveRunConflictError(object_type="batch", object_id=batch_id)
                run = self.repository.insert_batch_run(
                    session,
                    run_id=run_id,
                    batch_internal_id=batch.id,
                    status=BatchRunStatus.STARTING,
                    total_case_count=total_case_count,
                    started_at=now,
                    now=now,
                )
                batch.current_batch_run_id = run.id
                batch.status = batch_status
                batch.updated_at = now
                return self._batch_run_view(run, batch_id)
        except IntegrityError:
            existing = self._existing_batch_run_view(run_id, batch_id)
            if existing is not None:
                return existing
            raise ActiveRunConflictError(object_type="batch", object_id=batch_id) from None

    def create_case_run(
        self,
        *,
        batch_id: str,
        case_id: str,
        run_id: str,
        trigger_type: TriggerType,
        batch_run_id: str | None = None,
        case_status: CaseStatus = CaseStatus.ANALYZING,
        run_status: CaseRunStatus = CaseRunStatus.STARTING,
        started_at: datetime | None = None,
    ) -> CaseRunView:
        """幂等创建案例运行并切换 cases.current_case_run_id（规格 10.2/10.3）。"""
        now = _now(started_at)
        if trigger_type == TriggerType.MANUAL_RERUN and batch_run_id is not None:
            raise ValueError("MANUAL_RERUN 不允许关联首次批次运行（规格 10.3）")
        try:
            with self._transaction() as session:
                existing = self.repository.case_run_by_run_id(session, run_id)
                if existing is not None:
                    case = self.repository.case_by_internal_id(session, existing.case_id)
                    batch = (
                        self.repository.batch_by_internal_id(session, case.batch_id)
                        if case is not None
                        else None
                    )
                    return self._case_run_view(
                        existing,
                        batch.batch_id if batch is not None else batch_id,
                        case.case_id if case is not None else case_id,
                    )
                batch = self.repository.batch_by_batch_id(session, batch_id)
                if batch is None:
                    raise RunStoreResourceNotFoundError(
                        object_type="batch", object_id=batch_id
                    )
                case = self.repository.case_of_batch(session, batch.id, case_id)
                if case is None:
                    raise RunStoreResourceNotFoundError(
                        object_type="case", object_id=case_id
                    )
                batch_run_internal_id: int | None = None
                if trigger_type == TriggerType.BATCH:
                    batch_run = (
                        self.repository.batch_run_by_run_id(session, batch_run_id)
                        if batch_run_id is not None
                        else None
                    )
                    if batch_run is None:
                        raise RunStoreResourceNotFoundError(
                            object_type="batch_run", object_id=batch_run_id or ""
                        )
                    if batch_run.batch_id != batch.id:
                        raise RunStoreResourceNotFoundError(
                            object_type="batch_run", object_id=batch_run_id or ""
                        )
                    batch_run_internal_id = batch_run.id
                run = self.repository.insert_case_run(
                    session,
                    run_id=run_id,
                    case_internal_id=case.id,
                    batch_run_internal_id=batch_run_internal_id,
                    previous_case_run_id=case.current_case_run_id,
                    trigger_type=trigger_type,
                    status=run_status,
                    current_stage=None,
                    started_at=now,
                    now=now,
                )
                case.current_case_run_id = run.id
                case.status = case_status
                case.updated_at = now
                self._refresh_batch_projection(session, batch.id, now)
                return self._case_run_view(run, batch_id, case_id)
        except IntegrityError:
            existing = self._existing_case_run_view(run_id, batch_id, case_id)
            if existing is not None:
                return existing
            raise ActiveRunConflictError(object_type="case", object_id=case_id) from None

    # ---------- 阶段事件追加（规格 9.1/9.2/11.1/11.2） ----------

    def record_stage_started(
        self,
        *,
        case_run_id: int,
        stage_name: str,
        status: CaseRunStatus,
        occurred_at: datetime | None = None,
    ) -> None:
        """STAGE_STARTED：更新当前 case_run 的 current_stage 与内部状态。"""
        now = _now(occurred_at)
        with self._transaction() as session:
            run = self._require_active_case_run(session, case_run_id)
            run.current_stage = stage_name
            run.status = status
            run.updated_at = now

    def record_model_attempt(
        self, *, case_run_id: int, attempt: ModelAttemptInput
    ) -> None:
        """MODEL_ATTEMPT_FINISHED：追加 model_calls（幂等按 call_id；规格 9.2）。"""
        now = _now(None)
        with self._transaction() as session:
            existing = self.repository.model_call_by_call_id(session, attempt.call_id)
            if existing is not None:
                return
            run = self._require_active_case_run(session, case_run_id)
            self.repository.insert_model_call(
                session, case_run_id=run.id, attempt=attempt, now=now
            )

    def record_stage_result(
        self,
        *,
        case_run_id: int,
        stage: StageResultInput,
        occurred_at: datetime | None = None,
    ) -> None:
        """STAGE_RESULT_VALIDATED：追加 stage_results（只追加不覆盖，规格 11.2）。"""
        now = _now(occurred_at)
        with self._transaction() as session:
            run = self._require_active_case_run(session, case_run_id)
            existing = self.repository.stage_result_of_run(session, run.id, stage.stage_name)
            if existing is not None:
                if existing.result_sha256 == stage.result_sha256:
                    return
                raise StageResultConflictError(
                    object_id=run.run_id, stage_name=stage.stage_name
                )
            self.repository.insert_stage_result(
                session,
                case_run_id=run.id,
                stage_name=stage.stage_name,
                contract_version=stage.contract_version,
                result_json=stage.result_json,
                result_sha256=stage.result_sha256,
                now=now,
            )

    # ---------- 失败记录（规格 10.2/10.3） ----------

    def record_failure(
        self,
        *,
        case_run_id: int,
        error_code: str,
        error_stage: str,
        error_detail_json: dict[str, Any] | None = None,
        case_status: CaseStatus = CaseStatus.PROCESSING_ERROR,
        run_status: CaseRunStatus = CaseRunStatus.FAILED,
        occurred_at: datetime | None = None,
    ) -> FailureResult:
        """记录技术失败：case_run FAILED + 错误字段、案例 PROCESSING_ERROR，
        同事务更新批次当前投影与首次批量运行异常计数（规格 10.2/10.3）。"""
        now = _now(occurred_at)
        with self._transaction() as session:
            run = self.repository.case_run_by_id(session, case_run_id)
            if run is None:
                raise RunStoreResourceNotFoundError(
                    object_type="case_run", object_id=str(case_run_id)
                )
            case = self.repository.case_by_internal_id(session, run.case_id)
            if case is None:
                raise RunStoreResourceNotFoundError(
                    object_type="case", object_id=str(run.case_id)
                )
            if run.status == CaseRunStatus.FAILED and run.error_code == error_code:
                batch = self.repository.batch_by_internal_id(session, case.batch_id)
                return self._failure_result(run, case, batch, error_code)
            self._require_active_case_run(session, case_run_id)
            run.status = run_status
            run.error_code = error_code
            run.error_stage = error_stage
            run.error_detail_json = error_detail_json
            run.finished_at = now
            run.updated_at = now
            case.status = case_status
            case.updated_at = now
            if run.batch_run_id is not None:
                self.repository.increment_batch_run_error(session, run.batch_run_id, now)
            self._refresh_batch_projection(session, case.batch_id, now)
            batch = self.repository.batch_by_internal_id(session, case.batch_id)
            return self._failure_result(run, case, batch, error_code)

    @staticmethod
    def _failure_result(
        run: CaseRun, case: Case, batch: Batch | None, error_code: str
    ) -> FailureResult:
        if batch is None:
            raise RunStoreResourceNotFoundError(
                object_type="batch", object_id=str(case.batch_id)
            )
        return FailureResult(
            case_run_id=run.id,
            run_id=run.run_id,
            batch_id=batch.batch_id,
            case_id=case.case_id,
            error_code=error_code,
            batch_status=batch.status.value,
            analysis_succeeded_count=batch.analysis_succeeded_count,
            error_count=batch.error_count,
        )

    # ---------- 完整决策包原子发布（规格 10.4） ----------

    def publish_complete_result(
        self,
        *,
        case_run_id: int,
        final_stage: StageResultInput,
        system_intervention_level: str | None = None,
        case_status: CaseStatus = CaseStatus.PENDING_REVIEW,
        run_status: CaseRunStatus = CaseRunStatus.SUCCEEDED,
        occurred_at: datetime | None = None,
    ) -> PublishResult:
        """完整决策包原子发布：最终阶段结果、case_run 成功、当前指针、案例
        PENDING_REVIEW 与批次当前状态/计数在同一事务提交（规格 10.4）。"""
        now = _now(occurred_at)
        with self._transaction() as session:
            run = self.repository.case_run_by_id(session, case_run_id)
            if run is None:
                raise RunStoreResourceNotFoundError(
                    object_type="case_run", object_id=str(case_run_id)
                )
            case = self.repository.case_by_internal_id(session, run.case_id)
            if case is None:
                raise RunStoreResourceNotFoundError(
                    object_type="case", object_id=str(run.case_id)
                )
            names = self.repository.stage_result_names(session, {run.id}).get(
                run.id, frozenset()
            )
            complete = _COMPLETE_PACKAGE_SET.issubset(names)
            if (
                run.status == run_status
                and case.current_case_run_id == run.id
                and case.status in (case_status, CaseStatus.COMPLETED)
                and complete
            ):
                batch = self.repository.batch_by_internal_id(session, case.batch_id)
                return self._publish_result(run, case, batch)
            self._require_active_case_run(session, case_run_id)
            if final_stage.stage_name not in _COMPLETE_PACKAGE_SET:
                raise IncompleteDecisionPackageError(
                    object_id=run.run_id, missing_stages=(final_stage.stage_name,)
                )
            missing = [
                name
                for name in COMPLETE_PACKAGE_STAGES
                if name not in names and name != final_stage.stage_name
            ]
            if missing:
                raise IncompleteDecisionPackageError(
                    object_id=run.run_id, missing_stages=tuple(missing)
                )
            existing_final = self.repository.stage_result_of_run(
                session, run.id, final_stage.stage_name
            )
            if existing_final is not None:
                if existing_final.result_sha256 != final_stage.result_sha256:
                    raise StageResultConflictError(
                        object_id=run.run_id, stage_name=final_stage.stage_name
                    )
            else:
                self.repository.insert_stage_result(
                    session,
                    case_run_id=run.id,
                    stage_name=final_stage.stage_name,
                    contract_version=final_stage.contract_version,
                    result_json=final_stage.result_json,
                    result_sha256=final_stage.result_sha256,
                    now=now,
                )
            run.status = run_status
            run.current_stage = None
            run.finished_at = now
            run.updated_at = now
            case.current_case_run_id = run.id
            case.status = case_status
            if system_intervention_level is not None:
                case.system_intervention_level = InterventionLevel(
                    system_intervention_level
                )
            case.updated_at = now
            if run.batch_run_id is not None:
                self.repository.increment_batch_run_success(session, run.batch_run_id, now)
            self._refresh_batch_projection(session, case.batch_id, now)
            batch = self.repository.batch_by_internal_id(session, case.batch_id)
            return self._publish_result(run, case, batch)

    @staticmethod
    def _publish_result(run: CaseRun, case: Case, batch: Batch | None) -> PublishResult:
        if batch is None:
            raise RunStoreResourceNotFoundError(
                object_type="batch", object_id=str(case.batch_id)
            )
        return PublishResult(
            case_run_id=run.id,
            run_id=run.run_id,
            batch_id=batch.batch_id,
            case_id=case.case_id,
            batch_status=batch.status.value,
            analysis_succeeded_count=batch.analysis_succeeded_count,
            error_count=batch.error_count,
        )

    # ---------- 完成首次批次运行（规格 10.3：冻结历史统计） ----------

    def finish_batch_run(
        self,
        *,
        batch_run_id: int,
        status: BatchRunStatus,
        finished_at: datetime | None = None,
    ) -> BatchRunView:
        """M3 判定首次批量分析结束：关闭 batch_run，历史统计不再变化。"""
        now = _now(finished_at)
        if status not in _TERMINAL_BATCH_RUN_STATUSES:
            raise ValueError(f"不支持的批次运行结束状态: {status.value}")
        with self._transaction() as session:
            run = self.repository.batch_run_by_id(session, batch_run_id)
            if run is None:
                raise RunStoreResourceNotFoundError(
                    object_type="batch_run", object_id=str(batch_run_id)
                )
            if run.status in _TERMINAL_BATCH_RUN_STATUSES:
                batch = self.repository.batch_by_internal_id(session, run.batch_id)
                return self._batch_run_view(
                    run, batch.batch_id if batch is not None else ""
                )
            if run.status not in (BatchRunStatus.STARTING, BatchRunStatus.RUNNING):
                raise RunNotActiveError(object_id=run.run_id)
            run.status = status
            run.finished_at = now
            run.updated_at = now
            batch = self.repository.batch_by_internal_id(session, run.batch_id)
            return self._batch_run_view(
                run, batch.batch_id if batch is not None else ""
            )

    # ---------- 启动恢复检查（规格 10.5） ----------

    def recover_interrupted(self, *, now: datetime | None = None) -> RecoverySummary:
        """幂等启动恢复：活动运行标 INTERRUPTED、未发布案例进 PROCESSING_ERROR、
        活动批次运行标 INTERRUPTED、保留全部历史并重算受影响批次投影。"""
        now = _now(now)
        with self._transaction() as session:
            interrupted_case_runs = 0
            interrupted_batch_runs = 0
            error_cases = 0
            affected_batches: set[int] = set()
            for run in self.repository.active_case_runs(session):
                run.status = CaseRunStatus.INTERRUPTED
                run.finished_at = now
                run.updated_at = now
                interrupted_case_runs += 1
                case = self.repository.case_by_internal_id(session, run.case_id)
                if case is None:
                    continue
                affected_batches.add(case.batch_id)
                names = self.repository.stage_result_names(session, {run.id}).get(
                    run.id, frozenset()
                )
                published = (
                    case.current_case_run_id == run.id
                    and case.status in (CaseStatus.PENDING_REVIEW, CaseStatus.COMPLETED)
                    and _COMPLETE_PACKAGE_SET.issubset(names)
                )
                if not published:
                    run.error_code = APP_INTERRUPTED_CODE
                    run.error_stage = APP_RECOVERY_STAGE
                    run.error_detail_json = {
                        "note": "应用启动恢复：运行未作为完整结果发布",
                        "recovered_at": now.isoformat(),
                    }
                    case.status = CaseStatus.PROCESSING_ERROR
                    case.updated_at = now
                    error_cases += 1
            for batch_run in self.repository.active_batch_runs(session):
                batch_run.status = BatchRunStatus.INTERRUPTED
                batch_run.finished_at = now
                batch_run.updated_at = now
                interrupted_batch_runs += 1
                affected_batches.add(batch_run.batch_id)
            for batch_internal_id in affected_batches:
                self._refresh_batch_projection(session, batch_internal_id, now)
            return RecoverySummary(
                interrupted_case_runs=interrupted_case_runs,
                interrupted_batch_runs=interrupted_batch_runs,
                error_cases=error_cases,
                affected_batches=len(affected_batches),
            )

    # ---------- 批次当前投影重算（规格 10.3） ----------

    def _refresh_batch_projection(
        self, session: Session, batch_internal_id: int, now: datetime
    ) -> None:
        """按规格 10.3 从当前案例推导批次状态与三项计数，同事务写回 batches。"""
        cases = self.repository.cases_of_batch(session, batch_internal_id)
        runs = self.repository.runs_by_ids(
            session,
            (case.current_case_run_id for case in cases if case.current_case_run_id is not None),
        )
        names = self.repository.stage_result_names(session, runs)
        has_batch_runs = bool(
            self.repository.batch_runs_of_batch(session, batch_internal_id)
        )
        status = _batch_status(cases, runs, names, has_batch_runs)
        analysis_succeeded = sum(
            1
            for case in cases
            if case.status in (CaseStatus.PENDING_REVIEW, CaseStatus.COMPLETED)
            and _has_complete_package(case, runs, names)
        )
        error_count = sum(
            1 for case in cases if case.status == CaseStatus.PROCESSING_ERROR
        )
        self.repository.update_batch_projection(
            session,
            batch_internal_id=batch_internal_id,
            status=status,
            analysis_succeeded_count=analysis_succeeded,
            error_count=error_count,
            now=now,
        )

    # ---------- 只读历史（首次历史与运行历史，规格 10.3/11.2） ----------

    def batch_run_history(self, batch_id: str) -> list[BatchRunView]:
        """批次首次批量分析的完整历史（batch_runs 只保存首次统计）。"""
        with Session(self._engine) as session:
            batch = self.repository.batch_by_batch_id(session, batch_id)
            if batch is None:
                raise RunStoreResourceNotFoundError(object_type="batch", object_id=batch_id)
            rows = self.repository.batch_runs_history(session, batch.id)
            return [self._batch_run_view(row, batch_id) for row in rows]

    def case_run_history(self, batch_id: str, case_id: str) -> list[CaseRunView]:
        """案例全部运行历史（只追加不覆盖，规格 11.2）。"""
        with Session(self._engine) as session:
            batch = self.repository.batch_by_batch_id(session, batch_id)
            if batch is None:
                raise RunStoreResourceNotFoundError(object_type="batch", object_id=batch_id)
            case = self.repository.case_of_batch(session, batch.id, case_id)
            if case is None:
                raise RunStoreResourceNotFoundError(object_type="case", object_id=case_id)
            rows = self.repository.case_runs_history(session, case.id)
            return [self._case_run_view(row, batch_id, case_id) for row in rows]


__all__ = [
    "APP_INTERRUPTED_CODE",
    "APP_RECOVERY_STAGE",
    "COMPLETE_PACKAGE_STAGES",
    "RunStore",
]


