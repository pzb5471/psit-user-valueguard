"""M1-08：ReviewStore（技术实施规格 8/10.3/11.1/12.3/12.4）。

ReviewStore 对 M3 提供“短事务命令” submit_review：在独立同步 Session 中打开
一次事务、完成全部写入后提交；M3 不接触 Session、不自行提交（规格第 8 节）。

命令把正式人工确认结果原子写入 reviews 表，并同事务同步
cases.current_review_id/status/final_intervention_level 与批次当前投影
（规格 10.3 同源公式），随后返回与 M1-05 查询网关同构的 ReviewResultView
（系统原结果经 case_run_id 引用 stage_results，不复制第二份决策包）。

校验顺序（规格 12.3）：
1. submission_id 幂等命中直接返回已落库结果；
2. 批次/案例/案例运行不存在 → RESOURCE_NOT_FOUND（404）；
3. review_token 不匹配当前结果（重跑后旧 Token 失效）→ STALE_CASE_RESULT（409）；
4. 字段规则（12.3 表格）不满足 → REQUEST_VALIDATION_FAILED（422）；
5. 运行未 SUCCEEDED/不是当前结果 → STALE_CASE_RESULT（409）；案例不在
   PENDING_REVIEW 或已有审核 → CASE_ALREADY_COMPLETED（409）；
6. 同事务写入并返回 ReviewResultView；唯一约束冲突（并发同 case_id）→
   CASE_ALREADY_COMPLETED（409）。

显式假设（超出规格字面处在此声明，供 M2-01/M3-03 与人工 PR 复审）：
- review_token 与 M1-05 CaseQueryGateway 同算法 sha256("psit-review:
  {batch_id}:{case_id}:{run_id}")，本网关复制不 import；
- final_cause 只允许 {"cause_category": 六类之一}、final_actions 1—3 项且每项
  只允许 {"action_type": 六类之一}（M2-01 未冻结，本卡取最严格形态，禁止自由
  JSON/额外键）；execution_note 请求内按需出现并写入 reviews 表（规格 11.1
  九表），缺失时视图从 case_run 引用的 stage_results 顶层键回填；
- 状态转换机械不变式：同事务写 review + cases.current_review_id + status +
  final_intervention_level（仅人工提供时）；重跑只切换 current_case_run_id，
  已生成的人工确认仍指向旧运行（历史保留），因此重跑后该案例不可再提交；
- 案例级转换合法性（如 COMPLETED 禁止重跑）由 M3 在编排层裁决，本网关只执行
  机械不变式：不覆盖旧结果、每案例最多一份正式人工确认。
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.contracts.states import BatchStatus, CaseRunStatus, CaseStatus

from ..db.models import Case, CaseRun, InterventionLevel, Review, ReviewOutcome, StageResult
from ..queries.views import (
    ACTION_TYPE_OPTIONS,
    CAUSE_CATEGORY_OPTIONS,
    INTERVENTION_LEVEL_OPTIONS,
    ReviewResultView,
)
from .errors import (
    CaseAlreadyCompletedError,
    ReviewFieldValidationError,
    ReviewStoreResourceNotFoundError,
    StaleCaseResultError,
)
from .repository import ReviewStoreRepository
from .types import ReviewSubmitInput

#: 完整决策包的三个阶段名（规格 9/10.4；与 M1-07 RunStore 同源）。
_COMPLETE_PACKAGE_SET = frozenset(("perception", "attribution", "strategy"))

#: 规格 7.2/12.2 冻结枚举（与 M1-05 review_options 同源，禁止自由值）。
_OUTCOME_VALUES = frozenset(member.value for member in ReviewOutcome)
_INTERVENTION_LEVEL_VALUES = frozenset(item.value for item in INTERVENTION_LEVEL_OPTIONS)
_CAUSE_CATEGORY_VALUES = frozenset(item.value for item in CAUSE_CATEGORY_OPTIONS)
_ACTION_TYPE_VALUES = frozenset(item.value for item in ACTION_TYPE_OPTIONS)

#: 禁止在 APPROVED / INSUFFICIENT_EVIDENCE 出现的最终字段（规格 12.3 表格）。
_FINAL_FIELDS = ("final_intervention_level", "final_cause", "final_actions")


def _now(value: datetime | None) -> datetime:
    """命令时间戳：未显式传入时取当前 UTC（规格 11.2：UTC 毫秒时间）。"""
    return value if value is not None else datetime.now(UTC)


def _iso_utc(value: datetime) -> str:
    """ISO 序列化：SQLite 往返会丢失时区，按 UTC 语义补回偏移（规格 12.2）。"""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()


def _token(batch_id: str, case_id: str, run: CaseRun) -> str:
    """review_token 校验：与 M1-05 CaseQueryGateway 相同确定性算法（规格 12.3）。"""
    digest = hashlib.sha256(
        f"psit-review:{batch_id}:{case_id}:{run.run_id}".encode()
    )
    return digest.hexdigest()


def _non_empty_str(value: object) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _reject_final_fields(data: dict[str, Any]) -> None:
    """APPROVED / INSUFFICIENT_EVIDENCE 只允许共同字段，禁止 final_*（12.3）。"""
    for field in _FINAL_FIELDS:
        if data.get(field) is not None:
            raise ReviewFieldValidationError(
                message=f"该 outcome 禁止提供 {field}（仅 APPROVED/INSUFFICIENT_EVIDENCE 通用字段）"
            )


def _require_modified_fields(data: dict[str, Any], outcome: str) -> None:
    """MODIFIED_AND_APPROVED / REJECTED_WITH_JUDGMENT 的全部必填与键形态（12.3）。"""
    level = data.get("final_intervention_level")
    if not isinstance(level, str) or level not in _INTERVENTION_LEVEL_VALUES:
        raise ReviewFieldValidationError(
            message=(
                f"{outcome} 必须提供 final_intervention_level"
                "（MUST_INTERVENE/SHOULD_INTERVENE/NO_IMMEDIATE_INTERVENTION 之一）"
            )
        )
    final_cause = data.get("final_cause")
    if not isinstance(final_cause, dict) or set(final_cause.keys()) != {"cause_category"}:
        raise ReviewFieldValidationError(
            message=f"{outcome} 的 final_cause 只允许 {{'cause_category': 六类之一}}，禁止额外键"
        )
    category = final_cause.get("cause_category")
    if not isinstance(category, str) or category not in _CAUSE_CATEGORY_VALUES:
        raise ReviewFieldValidationError(
            message=f"{outcome} 的 final_cause.cause_category 必须为六类之一"
        )
    final_actions = data.get("final_actions")
    if not isinstance(final_actions, list) or not 1 <= len(final_actions) <= 3:
        raise ReviewFieldValidationError(
            message=f"{outcome} 的 final_actions 必须为 1—3 项"
        )
    for item in final_actions:
        if not isinstance(item, dict) or set(item.keys()) != {"action_type"}:
            raise ReviewFieldValidationError(
                message=(
                    f"{outcome} 的 final_actions 每项只允许 "
                    "{{'action_type': 六类之一}}，禁止额外键"
                ),
            )
        action_type = item.get("action_type")
        if not isinstance(action_type, str) or action_type not in _ACTION_TYPE_VALUES:
            raise ReviewFieldValidationError(
                message=f"{outcome} 的 final_actions 每项 action_type 必须为六类之一"
            )
    if not _non_empty_str(data.get("review_reason")):
        raise ReviewFieldValidationError(message=f"{outcome} 必须提供 review_reason")


def _validate_payload(data: dict[str, Any]) -> None:
    """规格 12.3 表格字段规则；data 为 ReviewSubmitInput 转出的 dict。"""
    outcome = data.get("outcome")
    if not isinstance(outcome, str) or outcome not in _OUTCOME_VALUES:
        raise ReviewFieldValidationError(
            message=(
                "outcome 必须为 APPROVED/MODIFIED_AND_APPROVED/"
                "REJECTED_WITH_JUDGMENT/INSUFFICIENT_EVIDENCE 之一"
            )
        )
    if outcome == "APPROVED" or outcome == "INSUFFICIENT_EVIDENCE":
        _reject_final_fields(data)
        if outcome == "INSUFFICIENT_EVIDENCE" and not _non_empty_str(
            data.get("review_reason")
        ):
            raise ReviewFieldValidationError(
                message="INSUFFICIENT_EVIDENCE 必须提供 review_reason"
            )
        return
    _require_modified_fields(data, outcome)


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
    """批次状态由当前案例推导（规格 10.3；与 RunStore 同源公式）。"""
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


def _result_by_stage(
    results: list[StageResult], stage_name: str
) -> dict[str, Any] | None:
    for result in results:
        if result.stage_name == stage_name:
            return result.result_json
    return None


def _top_level(results: list[StageResult], key: str) -> Any:
    """当前运行各阶段结果的约定顶层键（出现顺序为阶段插入顺序）。"""
    for result in results:
        value = result.result_json.get(key)
        if value is not None:
            return value
    return None


def _requires_list(value: Any) -> list[Any] | None:
    return value if isinstance(value, list) else None


def _review_result_view(
    review: Review, results: list[StageResult]
) -> ReviewResultView:
    """人工确认投影：落库人工值优先，缺省值经 case_run_id 引用阶段结果回填。"""
    attribution = _result_by_stage(results, "attribution")
    strategy = _result_by_stage(results, "strategy")
    final_intervention_level = (
        review.final_intervention_level.value
        if review.final_intervention_level is not None
        else None
    )
    final_cause = review.final_cause_json
    final_actions = review.final_actions_json
    # 仅“直接通过”表示人工完整认可系统结果。证据不足代表拒绝当前判断，
    # 不得把系统原因和动作伪装成最终人工结论。
    if review.outcome == ReviewOutcome.APPROVED:
        if final_intervention_level is None and strategy is not None:
            final_intervention_level = strategy.get("intervention_level")
        if final_cause is None and attribution is not None:
            final_cause = attribution.get("primary_cause")
        if final_actions is None and strategy is not None:
            final_actions = strategy.get("actions")
    return ReviewResultView(
        outcome=review.outcome.value,
        final_intervention_level=final_intervention_level,
        final_cause=final_cause if isinstance(final_cause, dict) else None,
        final_actions=_requires_list(final_actions),
        execution_note=review.execution_note or _top_level(results, "execution_note"),
        review_reason=review.review_reason,
        created_at=_iso_utc(review.created_at),
    )


class ReviewStore:
    """SQLite 版 ReviewStore：正式人工确认结果的短事务命令网关。"""

    def __init__(self, *, engine: Engine) -> None:
        self._engine = engine
        self.repository = ReviewStoreRepository(engine)

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

    def _existing_review_view(self, submission_id: str) -> ReviewResultView | None:
        """并发重入兜底：按 submission_id 读回已提交的人工确认（幂等返回）。"""
        with Session(self._engine) as session:
            review = self.repository.review_by_submission_id(session, submission_id)
            if review is None:
                return None
            results = self.repository.stage_results_of_run(session, review.case_run_id)
            return _review_result_view(review, results)

    def _existing_review_of_case(self, case_run_id: int) -> Review | None:
        """并发兜底：同一案例已有正式人工确认（uq_reviews_case_id 冲突）。"""
        with Session(self._engine) as session:
            run = self.repository.case_run_by_id(session, case_run_id)
            if run is None:
                return None
            case = self.repository.case_by_internal_id(session, run.case_id)
            if case is None:
                return None
            return self.repository.review_of_case(session, case.id)

    def _refresh_batch_projection(
        self, session: Session, batch_internal_id: int, now: datetime
    ) -> None:
        """按规格 10.3 从当前案例推导批次状态与三项计数，同事务写回 batches。"""
        cases = self.repository.cases_of_batch(session, batch_internal_id)
        runs = self.repository.runs_by_ids(
            session,
            (
                case.current_case_run_id
                for case in cases
                if case.current_case_run_id is not None
            ),
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

    def submit_review(
        self,
        *,
        submission_id: str,
        case_run_id: int,
        review_token: str,
        payload: ReviewSubmitInput,
        case_status: CaseStatus = CaseStatus.COMPLETED,
        occurred_at: datetime | None = None,
    ) -> ReviewResultView:
        """正式人工确认：单事务写入 reviews 并同步案例/批次投影（规格 12.3）。"""
        now = _now(occurred_at)
        data = asdict(payload)
        try:
            with self._transaction() as session:
                existing = self.repository.review_by_submission_id(session, submission_id)
                if existing is not None:
                    results = self.repository.stage_results_of_run(
                        session, existing.case_run_id
                    )
                    return _review_result_view(existing, results)
                run = self.repository.case_run_by_id(session, case_run_id)
                if run is None:
                    raise ReviewStoreResourceNotFoundError(
                        object_type="case_run", object_id=str(case_run_id)
                    )
                case = self.repository.case_by_internal_id(session, run.case_id)
                if case is None:
                    raise ReviewStoreResourceNotFoundError(
                        object_type="case", object_id=str(run.case_id)
                    )
                batch = self.repository.batch_by_internal_id(session, case.batch_id)
                if batch is None:
                    raise ReviewStoreResourceNotFoundError(
                        object_type="batch", object_id=str(case.batch_id)
                    )
                if _token(batch.batch_id, case.case_id, run) != review_token:
                    raise StaleCaseResultError(object_id=run.run_id)
                _validate_payload(data)
                if (
                    run.status != CaseRunStatus.SUCCEEDED
                    or case.current_case_run_id != run.id
                ):
                    raise StaleCaseResultError(object_id=run.run_id)
                if (
                    case.status != CaseStatus.PENDING_REVIEW
                    or case.current_review_id is not None
                ):
                    raise CaseAlreadyCompletedError(object_id=case.case_id)
                final_level = (
                    InterventionLevel(data["final_intervention_level"])
                    if data["final_intervention_level"] is not None
                    else None
                )
                review = self.repository.insert_review(
                    session,
                    review_id=f"review-{submission_id}",
                    submission_id=submission_id,
                    case_internal_id=case.id,
                    case_run_internal_id=run.id,
                    outcome=ReviewOutcome(data["outcome"]),
                    final_intervention_level=final_level,
                    final_cause_json=data["final_cause"],
                    final_actions_json=data["final_actions"],
                    review_reason=data["review_reason"],
                    execution_note=data["execution_note"],
                    now=now,
                )
                self.repository.update_case_review(
                    session,
                    case_internal_id=case.id,
                    review_internal_id=review.id,
                    status=case_status,
                    final_intervention_level=final_level,
                    now=now,
                )
                self._refresh_batch_projection(session, case.batch_id, now)
                results = self.repository.stage_results_of_run(session, run.id)
                return _review_result_view(review, results)
        except IntegrityError:
            existing = self._existing_review_view(submission_id)
            if existing is not None:
                return existing
            duplicate = self._existing_review_of_case(case_run_id)
            if duplicate is not None:
                raise CaseAlreadyCompletedError(
                    object_id=str(duplicate.case_id)
                ) from None
            raise


__all__ = ["ReviewStore"]
