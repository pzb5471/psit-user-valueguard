"""M1-08：ReviewStore 内存测试替身（与真网关同签名/同错误码/同返回类型）。

契约测试用：SQLite 真网关与内存替身执行同一组断言，锁定 M1-08 对外合同
（规格 12.3/12.4）。替身内部复制真网关的校验顺序、字段规则与状态转换；
字段规则直接复用 review_store.gateway 的模块级纯函数 _validate_payload
（同源不重复实现）。seed_* / advance_* 方法注入与 RunStore 发布后等价的
基线状态（已导入批次、SUCCEEDED 运行、三阶段 stage_results、PENDING_REVIEW
案例），供契约测试构造场景。
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.engine import Engine

from app.contracts.states import CaseRunStatus, CaseStatus
from app.modules.data.db.models import InterventionLevel, ReviewOutcome
from app.modules.data.queries.views import ReviewResultView
from app.modules.data.review_store.errors import (
    CaseAlreadyCompletedError,
    ReviewStoreResourceNotFoundError,
    StaleCaseResultError,
)
from app.modules.data.review_store.gateway import _validate_payload
from app.modules.data.review_store.types import ReviewSubmitInput

#: 完整决策包的三个阶段名（规格 9/10.4；与 M1-07 RunStore 同源）。
_COMPLETE_PACKAGE_SET = frozenset(("perception", "attribution", "strategy"))


def _review_token(batch_id: str, case_id: str, run_id: str) -> str:
    """与 M1-05/ReviewStore 相同确定性算法（复制不 import，防 ORM 形状耦合）。"""
    digest = hashlib.sha256(f"psit-review:{batch_id}:{case_id}:{run_id}".encode())
    return digest.hexdigest()


class FakeReviewStore:
    """内存版 ReviewStore：同签名/同错误码/同返回类型，无数据库依赖。

    状态以内部字典保存（batches/cases/case_runs/stage_results/reviews），
    行为对齐 ReviewStore.submit_review：校验顺序（幂等 → 404 → token →
    字段 → 当前运行 → 已完成）、同事务语义（失败不改变状态）、视图回填
    （系统原结果经 case_run_id 引用 stage_results，不复制第二份决策包）。
    """

    def __init__(self, *, engine: Engine | None = None) -> None:
        self._engine = engine
        self._next_id = 1
        self._batches: dict[int, dict[str, Any]] = {}
        self._batch_by_id: dict[str, int] = {}
        self._cases: dict[int, dict[str, Any]] = {}
        self._case_by_public: dict[tuple[str, str], int] = {}
        self._case_runs: dict[int, dict[str, Any]] = {}
        self._stage_results: list[dict[str, Any]] = []
        self._reviews: dict[int, dict[str, Any]] = {}
        self._review_by_submission: dict[str, int] = {}
        self._review_by_case: dict[int, int] = {}

    # ---------- 测试注入（与 RunStore 发布后状态等价） ----------

    def seed_batch(self, *, batch_id: str, status: str = "ANALYZING") -> int:
        """注入一个批次；提交后状态/计数由投影重算覆盖。"""
        internal_id = self._next_id
        self._next_id += 1
        self._batches[internal_id] = {
            "id": internal_id,
            "batch_id": batch_id,
            "status": status,
            "analysis_succeeded_count": 0,
            "error_count": 0,
            "updated_at": datetime.now(UTC),
        }
        self._batch_by_id[batch_id] = internal_id
        return internal_id

    def seed_case(
        self,
        *,
        batch_id: str,
        case_id: str,
        status: str | CaseStatus = CaseStatus.PENDING_REVIEW,
        current_case_run_id: int | None = None,
        current_review_id: int | None = None,
        system_intervention_level: str | None = None,
        final_intervention_level: str | None = None,
    ) -> int:
        """注入一个案例；batch 必须先 seed，返回内部案例 id。"""
        batch_internal_id = self._batch_by_id[batch_id]
        internal_id = self._next_id
        self._next_id += 1
        self._cases[internal_id] = {
            "id": internal_id,
            "batch_id_internal": batch_internal_id,
            "batch_id": batch_id,
            "case_id": case_id,
            "status": (
                status if isinstance(status, CaseStatus) else CaseStatus(status)
            ),
            "system_intervention_level": system_intervention_level,
            "final_intervention_level": final_intervention_level,
            "current_case_run_id": current_case_run_id,
            "current_review_id": current_review_id,
            "updated_at": datetime.now(UTC),
        }
        self._case_by_public[(batch_id, case_id)] = internal_id
        return internal_id

    def seed_case_run(
        self,
        *,
        case_run_id: int,
        run_id: str,
        case_internal_id: int,
        status: str | CaseRunStatus = CaseRunStatus.SUCCEEDED,
    ) -> None:
        """注入一个案例运行；case 必须先 seed。"""
        case = self._cases[case_internal_id]
        self._case_runs[case_run_id] = {
            "id": case_run_id,
            "run_id": run_id,
            "case_id_internal": case_internal_id,
            "case_id": case["case_id"],
            "status": (
                status if isinstance(status, CaseRunStatus) else CaseRunStatus(status)
            ),
        }

    def seed_stage_result(
        self, *, case_run_id: int, stage_name: str, result_json: dict[str, Any]
    ) -> None:
        """注入某运行的一个阶段结果（视图回填用，替代 RunStore.record_stage_result）。"""
        self._stage_results.append(
            {
                "case_run_id": case_run_id,
                "stage_name": stage_name,
                "result_json": result_json,
            }
        )

    def advance_case_run(
        self,
        *,
        batch_id: str,
        case_id: str,
        case_run_id: int,
        run_id: str,
        status: str | CaseStatus = CaseStatus.PENDING_REVIEW,
    ) -> None:
        """模拟 RunStore 重跑：切换当前运行并发布，保留历史审核指针（规格 10.3）。"""
        case_internal = self._case_by_public[(batch_id, case_id)]
        self.seed_case_run(
            case_run_id=case_run_id,
            run_id=run_id,
            case_internal_id=case_internal,
            status="SUCCEEDED",
        )
        case = self._cases[case_internal]
        case["current_case_run_id"] = case_run_id
        case["status"] = (
            status if isinstance(status, CaseStatus) else CaseStatus(status)
        )
        case["updated_at"] = datetime.now(UTC)

    # ---------- 读取（契约断言用） ----------

    def batch_status(self, batch_id: str) -> str:
        """当前批次投影状态（与真网关 batches.status 同语义）。"""
        return self._batches[self._batch_by_id[batch_id]]["status"]

    # ---------- 命令 ----------

    def submit_review(
        self,
        *,
        submission_id: str,
        case_run_id: int,
        review_token: str,
        payload: ReviewSubmitInput,
        case_status: str | CaseStatus = CaseStatus.COMPLETED,
        occurred_at: datetime | None = None,
    ) -> ReviewResultView:
        """正式人工确认（规格 12.3）：校验顺序与状态转换对齐真网关。"""
        now = occurred_at if occurred_at is not None else datetime.now(UTC)
        data = asdict(payload)
        existing_id = self._review_by_submission.get(submission_id)
        if existing_id is not None:
            return self._view(self._reviews[existing_id])
        run = self._case_runs.get(case_run_id)
        if run is None:
            raise ReviewStoreResourceNotFoundError(
                object_type="case_run", object_id=str(case_run_id)
            )
        case = self._cases.get(run["case_id_internal"])
        if case is None:
            raise ReviewStoreResourceNotFoundError(
                object_type="case", object_id=str(run["case_id"])
            )
        batch = self._batches.get(case["batch_id_internal"])
        if batch is None:
            raise ReviewStoreResourceNotFoundError(
                object_type="batch", object_id=str(case["batch_id_internal"])
            )
        if (
            _review_token(batch["batch_id"], case["case_id"], run["run_id"])
            != review_token
        ):
            raise StaleCaseResultError(object_id=run["run_id"])
        _validate_payload(data)
        if (
            run["status"] != CaseRunStatus.SUCCEEDED
            or case["current_case_run_id"] != run["id"]
        ):
            raise StaleCaseResultError(object_id=run["run_id"])
        if (
            case["status"] != CaseStatus.PENDING_REVIEW
            or case["current_review_id"] is not None
        ):
            raise CaseAlreadyCompletedError(object_id=case["case_id"])
        final_level = (
            InterventionLevel(data["final_intervention_level"])
            if data["final_intervention_level"] is not None
            else None
        )
        review = self._insert_review(
            submission_id=submission_id,
            case_internal_id=case["id"],
            case_run_internal_id=run["id"],
            outcome=ReviewOutcome(data["outcome"]),
            final_intervention_level=final_level,
            final_cause_json=data["final_cause"],
            final_actions_json=data["final_actions"],
            review_reason=data["review_reason"],
            execution_note=data["execution_note"],
            now=now,
        )
        case["current_review_id"] = review["id"]
        case["status"] = (
            case_status
            if isinstance(case_status, CaseStatus)
            else CaseStatus(case_status)
        )
        if final_level is not None:
            case["final_intervention_level"] = final_level
        case["updated_at"] = now
        self._refresh_batch_projection(case, now)
        return self._view(review)

    # ---------- 内部实现 ----------

    def _insert_review(
        self,
        *,
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
    ) -> dict[str, Any]:
        """追加一份正式人工确认（review_id/submission_id/case_id 唯一语义）。"""
        internal_id = self._next_id
        self._next_id += 1
        review = {
            "id": internal_id,
            "review_id": f"review-{submission_id}",
            "submission_id": submission_id,
            "case_id": case_internal_id,
            "case_run_id": case_run_internal_id,
            "outcome": outcome,
            "final_intervention_level": final_intervention_level,
            "final_cause_json": final_cause_json,
            "final_actions_json": final_actions_json,
            "review_reason": review_reason,
            "execution_note": execution_note,
            "created_at": now,
        }
        self._reviews[internal_id] = review
        self._review_by_submission[submission_id] = internal_id
        self._review_by_case[case_internal_id] = internal_id
        return review

    def _refresh_batch_projection(self, case: dict[str, Any], now: datetime) -> None:
        """按规格 10.3 从当前案例推导批次状态与两项计数（与 RunStore 同源公式）。"""
        batch_internal_id = case["batch_id_internal"]
        cases = [
            item
            for item in self._cases.values()
            if item["batch_id_internal"] == batch_internal_id
        ]
        analysis_succeeded = sum(
            1
            for item in cases
            if item["status"] in (CaseStatus.PENDING_REVIEW, CaseStatus.COMPLETED)
            and self._has_complete_package(item)
        )
        error_count = sum(
            1 for item in cases if item["status"] == CaseStatus.PROCESSING_ERROR
        )
        batch = self._batches[batch_internal_id]
        batch["status"] = self._batch_status(cases)
        batch["analysis_succeeded_count"] = analysis_succeeded
        batch["error_count"] = error_count
        batch["updated_at"] = now

    def _has_complete_package(self, case: dict[str, Any]) -> bool:
        """完整决策包：当前 case_run 且三阶段结果齐备（规格 10.3/10.4）。"""
        current_run = case["current_case_run_id"]
        if current_run is None:
            return False
        names = {
            item["stage_name"]
            for item in self._stage_results
            if item["case_run_id"] == current_run
        }
        return _COMPLETE_PACKAGE_SET.issubset(names)

    def _batch_status(self, cases: list[dict[str, Any]]) -> str:
        """批次状态由当前案例推导（规格 10.3；与 RunStore 同源公式）。"""
        statuses = [item["status"] for item in cases]
        if any(status == CaseStatus.ANALYZING for status in statuses):
            return "ANALYZING"
        if any(status == CaseStatus.PROCESSING_ERROR for status in statuses):
            return "COMPLETED_WITH_ERRORS"
        if all(status == CaseStatus.PENDING_ANALYSIS for status in statuses):
            return "PENDING_ANALYSIS"
        if all(
            status in (CaseStatus.PENDING_REVIEW, CaseStatus.COMPLETED)
            for status in statuses
        ) and all(self._has_complete_package(item) for item in cases):
            return "COMPLETED"
        return "ANALYZING"

    def _view(self, review: dict[str, Any]) -> ReviewResultView:
        """人工确认投影：落库人工值优先，缺省值经 case_run_id 引用阶段结果回填。"""
        results = [
            item
            for item in self._stage_results
            if item["case_run_id"] == review["case_run_id"]
        ]
        attribution = next(
            (
                item["result_json"]
                for item in results
                if item["stage_name"] == "attribution"
            ),
            None,
        )
        strategy = next(
            (item["result_json"] for item in results if item["stage_name"] == "strategy"),
            None,
        )
        final_intervention_level = (
            review["final_intervention_level"].value
            if review["final_intervention_level"] is not None
            else None
        )
        final_cause = review["final_cause_json"]
        final_actions = review["final_actions_json"]
        if review["outcome"] == ReviewOutcome.APPROVED:
            if final_intervention_level is None and strategy is not None:
                final_intervention_level = strategy.get("intervention_level")
            if final_cause is None and attribution is not None:
                final_cause = attribution.get("primary_cause")
            if final_actions is None and strategy is not None:
                final_actions = strategy.get("actions")
        execution_note = review["execution_note"] or next(
            (
                item["result_json"].get("execution_note")
                for item in results
                if item["result_json"].get("execution_note") is not None
            ),
            None,
        )
        return ReviewResultView(
            outcome=review["outcome"].value,
            final_intervention_level=final_intervention_level,
            final_cause=final_cause if isinstance(final_cause, dict) else None,
            final_actions=final_actions if isinstance(final_actions, list) else None,
            execution_note=execution_note,
            review_reason=review["review_reason"],
            created_at=review["created_at"].isoformat(),
        )


__all__ = ["FakeReviewStore"]
