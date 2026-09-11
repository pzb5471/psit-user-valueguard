"""M1-05：CaseQueryGateway（技术实施规格 8/10.3/12.1/12.2；ADR-0079）。

按 batch_id、case_id、固定筛选和分页提供稳定业务投影：

- 批次列表：imported_at 倒序、batch_id 升序稳定排序；limit 默认 20、1—100，
  offset 默认 0；
- 案例队列：固定按最终人工或系统介入等级（1/2/3，NULL 最后）、imported_at、
  case_id 排序，页面不能传 sort_by；只允许一个 status 和一个
  intervention_level 筛选，limit 默认 50；
- 批次状态与三项计数从当前案例 + 当前 case_run 实时聚合（规格 10.3），
  不信任 batches 存量列（M1-07 RunStore 尚未开始写运行历史的过渡期聚合）；
- 详情只投影当前 case_run 的阶段结果与人工确认结果；首次历史（batch_run）
  不与当前投影混用，用于“当前与首次历史分离”断言；
- 资源不存在抛 LookupError，参数非法抛 ValueError；不返回 ORM、Session、
  内部整数主键或运行编号（规格 8 禁止事项）。

显式假设（超出规格字面处在此声明，供 M2-01/M3-03 与人工 PR 复审）：
- 案例排序中 NULL 介入等级排最后（升序 1/2/3/NULL，再 imported_at/case_id
  升序），整个“升序”为本网关假设，已由测试锁定并请人工复核；
- review_token 为确定性不透明值 sha256("psit-review:{batch_id}:{case_id}:
  {run_id}")，M1-08 以相同算法校验；重跑后 run_id 变化使旧 Token 失效
  （规格 12.3：结果被重跑替换后 Token 必须变化）；
- can_rerun=status∈(PENDING_REVIEW, PROCESSING_ERROR) 且无活动 case_run
  （规格 10.2：PENDING_ANALYSIS 不能走单案例重跑、COMPLETED 不允许重跑）；
- execution_note 优先读取人工确认记录，缺失时从策略结果约定键回退；
- has_evidence_conflict/has_insufficient_evidence/has_modality_failure 从
  当前结果的约定布尔键读取，has_modality_failure 额外在证据读取/图片格式
  错误时置真（规格 12.2）；M2-01 冻结结果合同后对齐键名；
- processing_error 的中文 message/next_action 由错误编号映射表生成；
- analysis_unavailable_message 属于 M2/M3 的模型可用性判断，不由本网关输出。
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.engine import Engine

from app.contracts.data import CaseInput
from app.contracts.states import BatchStatus, CaseRunStatus, CaseStatus

from ..db.models import Batch, Case, CaseRun, Evidence, Review, ReviewOutcome, StageResult
from ..repositories.case_query_repository import CaseQueryRepository
from .views import (
    BatchListView,
    BatchWorkspaceView,
    CaseDetailView,
    CaseProcessingErrorView,
    CaseQueueItemView,
    CaseQueueView,
    CitedEvidenceView,
    ProcessingErrorStage,
    ReviewResultView,
    build_review_options,
)

_CASE_RUN_ACTIVE = (
    CaseRunStatus.STARTING,
    CaseRunStatus.PERCEPTION_RUNNING,
    CaseRunStatus.ATTRIBUTION_RUNNING,
    CaseRunStatus.STRATEGY_RUNNING,
)

_INTERVENTION_RANK = {
    "MUST_INTERVENE": 1,
    "SHOULD_INTERVENE": 2,
    "NO_IMMEDIATE_INTERVENTION": 3,
}

#: 三个队列标记的结果 JSON 约定键（规格 12.2；M2-01 冻结后对齐键名）。
_FLAG_KEYS = {
    "has_evidence_conflict": "conflict",
    "has_insufficient_evidence": "insufficient",
    "has_modality_failure": "modality",
}

_MODALITY_ERROR_CODES = frozenset({"EVIDENCE_READ_FAILED", "EVIDENCE_MEDIA_INVALID"})

#: 处理异常的内部阶段 -> 业务化 stage（规格 12.2：只暴露五个业务阶段）。
_ERROR_BUSINESS_STAGE: dict[str, ProcessingErrorStage] = {
    "input_preparation": "INPUT_PREPARATION",
    "perception": "EVIDENCE_PROCESSING",
    "image": "EVIDENCE_PROCESSING",
    "evidence": "EVIDENCE_PROCESSING",
    "attribution": "AI_ANALYSIS",
    "strategy": "AI_ANALYSIS",
    "result_persistence": "RESULT_PERSISTENCE",
    "app_recovery": "APP_RECOVERY",
}

#: 固定错误编号 -> 中文 message / next_action（规格 12.4；供 business 化展示）。
_ERROR_MESSAGES: dict[str, tuple[str, str]] = {
    "EVIDENCE_READ_FAILED": ("证据文件读取失败", "检查证据文件后重新分析"),
    "EVIDENCE_MEDIA_INVALID": ("图片格式或内容无效", "更换有效图片后重新分析"),
    "MODEL_AUTH_FAILED": ("模型服务认证失败", "检查模型服务配置后重试"),
    "MODEL_TIMEOUT": ("模型调用超时", "稍后重试或人工核验"),
    "MODEL_RATE_LIMITED": ("模型调用频率受限", "稍后重试"),
    "MODEL_RESPONSE_INVALID": ("模型返回结果不符合合同", "稍后重试"),
    "MODEL_ATTEMPTS_EXHAUSTED": ("模型调用次数耗尽", "稍后重试或人工核验"),
    "RESULT_PERSISTENCE_FAILED": ("结果保存失败", "查看技术日志后重试"),
    "APP_INTERRUPTED": ("应用中断导致分析未完成", "重新开始分析"),
    "UNEXPECTED_PROCESSING_ERROR": ("处理过程发生未预期错误", "查看技术日志后重试"),
}

_EVIDENCE_REF_KEYS = frozenset(
    {"support_evidence", "conflicting_evidence", "conflict_evidence", "evidence"}
)
_EVIDENCE_LABELS = {
    "text": "客户对话",
    "image": "售后图片",
    "behavior": "订单与客户价值事实",
}
_FACT_LABELS = {
    "HIGH_VALUE_CUSTOMER": "高价值客户标识",
    "ORDER_STATUS": "订单状态",
    "ORDER_PURCHASED_AT": "下单时间",
    "ORDER_PAYMENT_TOTAL": "订单支付总额",
}


def _required_limit(value: int | None, default: int) -> int:
    """limit 校验：默认 20（批次）或 50（案例），必须为 1—100 整数（规格 12.1）。"""
    resolved = default if value is None else value
    if not isinstance(resolved, int) or isinstance(resolved, bool) or not 1 <= resolved <= 100:
        raise ValueError("limit 必须为 1—100 的整数")
    return resolved


def _required_offset(value: int | None) -> int:
    """offset 校验：默认 0，必须为非负整数（规格 12.1）。"""
    resolved = 0 if value is None else value
    if not isinstance(resolved, int) or isinstance(resolved, bool) or resolved < 0:
        raise ValueError("offset 必须为非负整数")
    return resolved


def _validate_status_filter(status: str | None) -> None:
    """案例只允许一个 status 筛选（规格 12.1），值必须为 CaseStatus 合同值。"""
    if status is not None and status not in {member.value for member in CaseStatus}:
        raise ValueError(f"不支持的案例状态筛选: {status!r}")


def _validate_level_filter(level: str | None) -> None:
    """案例只允许一个 intervention_level 筛选（规格 12.1），值必须为三档合同值。"""
    if level is not None and level not in _INTERVENTION_RANK:
        raise ValueError(f"不支持的介入等级筛选: {level!r}")


def _case_level(case: Case) -> str | None:
    """当前有效介入等级：最终人工等级优先，否则系统等级（规格 12.1/12.2）。"""
    if case.final_intervention_level is not None:
        return case.final_intervention_level.value
    if case.system_intervention_level is not None:
        return case.system_intervention_level.value
    return None


def _intervention_rank(level: str | None) -> int:
    """介入等级排序位：1/2/3，NULL 排最后（规格 12.2 冻结排序）。"""
    if level is None:
        return 4
    return _INTERVENTION_RANK.get(level, 4)


def _is_mock(case: Case) -> bool:
    """is_mock 从数据身份读取（规格 12.2）；当前 mock_dataset_v1 恒为 simulated。"""
    return bool((case.case_input_json or {}).get("data_identity") == "simulated")


def _has_complete_package(
    case: Case, runs: dict[int, CaseRun], counts: dict[int, int]
) -> bool:
    """完整决策包：当前 case_run 存在且至少有一份阶段结果（规格 10.3/10.4）。"""
    if case.current_case_run_id is None or case.current_case_run_id not in runs:
        return False
    return counts.get(case.current_case_run_id, 0) > 0


def _batch_status(
    cases: list[Case],
    runs: dict[int, CaseRun],
    counts: dict[int, int],
    has_batch_runs: bool,
) -> str:
    """批次状态由当前案例推导（规格 10.3），实时聚合不信任存量列。"""
    statuses = [case.status for case in cases]
    if any(status == CaseStatus.ANALYZING for status in statuses):
        return BatchStatus.ANALYZING.value
    if any(status == CaseStatus.PROCESSING_ERROR for status in statuses):
        return BatchStatus.COMPLETED_WITH_ERRORS.value
    if all(status == CaseStatus.PENDING_ANALYSIS for status in statuses) and not has_batch_runs:
        return BatchStatus.PENDING_ANALYSIS.value
    if all(
        status in (CaseStatus.PENDING_REVIEW, CaseStatus.COMPLETED)
        for status in statuses
    ) and all(_has_complete_package(case, runs, counts) for case in cases):
        return BatchStatus.COMPLETED.value
    # 兜底：混合状态或首次运行已开始但尚无完整结果，归为分析中。
    return BatchStatus.ANALYZING.value


def _scan_flags(
    value: object, flags: dict[str, bool], *, derive_missing: bool = False
) -> None:
    """从冻结结果合同结构推导队列标记，并兼容早期布尔夹具。"""
    if isinstance(value, dict):
        for key, child in value.items():
            if key in _FLAG_KEYS and child is True:
                flags[_FLAG_KEYS[key]] = True
            if key in {"conflicting_evidence", "conflict_evidence"} and child:
                flags["conflict"] = True
            if key == "relationship" and child == "CONFLICTS":
                flags["conflict"] = True
            # PerceptionResult 的 missing_evidence 表示该案例无法凭现有证据
            # 可靠判断；策略阶段的同名早期测试辅助字段不属于冻结合同。
            if key == "missing_evidence" and child and derive_missing:
                flags["insufficient"] = True
            if key == "cause_category" and child == "INSUFFICIENT_EVIDENCE":
                flags["insufficient"] = True
            _scan_flags(child, flags, derive_missing=derive_missing)
    elif isinstance(value, list):
        for child in value:
            _scan_flags(child, flags, derive_missing=derive_missing)


def _run_flags(
    results: list[StageResult], run: CaseRun | None
) -> tuple[bool, bool, bool]:
    """队列标记：当前结果约定键 + 证据/图片类技术失败（规格 12.2）。"""
    flags = {"conflict": False, "insufficient": False, "modality": False}
    for result in results:
        _scan_flags(
            result.result_json,
            flags,
            derive_missing=result.stage_name == "perception",
        )
    if run is not None and run.error_code in _MODALITY_ERROR_CODES:
        flags["modality"] = True
    return flags["conflict"], flags["insufficient"], flags["modality"]


def _processing_error(run: CaseRun | None) -> CaseProcessingErrorView:
    """仅 PROCESSING_ERROR 案例：业务化 code/message/stage/next_action/trace_id。"""
    code = run.error_code if run is not None and run.error_code else "UNEXPECTED_PROCESSING_ERROR"
    message, next_action = _ERROR_MESSAGES.get(
        code, ("处理过程发生异常", "查看技术日志后重试")
    )
    tag = (run.error_stage or "").strip().lower() if run is not None else ""
    stage = _ERROR_BUSINESS_STAGE.get(tag, "AI_ANALYSIS")
    trace_id = ""
    if run is not None and isinstance(run.error_detail_json, dict):
        trace_id = str(run.error_detail_json.get("trace_id") or "")
    return CaseProcessingErrorView(
        code=code,
        message=message,
        stage=stage,
        next_action=next_action,
        trace_id=trace_id,
    )


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


def _collect_cited_evidence_ids(
    results: list[StageResult], evidence_by_id: dict[str, Evidence]
) -> list[str]:
    """当前结果实际引用的证据编号（去重保序，且必须属于当前案例）。"""
    ids: dict[str, None] = {}

    def visit(value: object) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key in {"evidence_id", "image_evidence_id"} and isinstance(child, str):
                    ids.setdefault(child, None)
                elif key in _EVIDENCE_REF_KEYS and isinstance(child, list):
                    for item in child:
                        if isinstance(item, str):
                            ids.setdefault(item, None)
                        elif isinstance(item, dict) and isinstance(item.get("evidence_id"), str):
                            ids.setdefault(item["evidence_id"], None)
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    for result in results:
        visit(result.result_json)
    return [evidence_id for evidence_id in ids if evidence_id in evidence_by_id]


def _image_summary(perception: dict[str, Any] | None, evidence_id: str) -> str | None:
    """图片可显示摘要：感知结果中该图片的观察事实（不返回路径）。"""
    if perception is None:
        return None
    observations = perception.get("image_observations") or []
    if not isinstance(observations, list):
        return None
    for observation in observations:
        if not isinstance(observation, dict):
            continue
        observation_evidence_id = observation.get("image_evidence_id")
        if observation_evidence_id is None:
            observation_evidence_id = observation.get("evidence_id")
        if observation_evidence_id != evidence_id:
            continue
        facts = observation.get("observable_facts") or observation.get("facts") or []
        if facts:
            return "；".join(str(fact) for fact in facts)
    return None


def _behavior_summary(payload: dict[str, Any]) -> str | None:
    """行为/订单事实的可显示摘要（业务 label + 值，不含来源 JSON）。"""
    fact_type = str(payload.get("fact_type") or "")
    raw = payload.get("value")
    value_text = "是" if raw is True else ("否" if raw is False else str(raw or ""))
    label = _FACT_LABELS.get(fact_type, fact_type)
    return f"{label}：{value_text}" if value_text and value_text != "None" else label or None


def _cited_evidence_view(
    evidence: Evidence, perception: dict[str, Any] | None
) -> CitedEvidenceView:
    """单条被引用证据的业务视图（文本/行为给脱敏文本，图片给可显示摘要）。"""
    modality = evidence.modality
    payload = evidence.payload_json or {}
    text: str | None = None
    summary: str | None = None
    if modality == "text":
        raw = payload.get("text")
        text = str(raw) if raw is not None else None
    elif modality == "image":
        summary = _image_summary(perception, evidence.evidence_id)
    elif modality == "behavior":
        text = _behavior_summary(payload)
    return CitedEvidenceView(
        evidence_id=evidence.evidence_id,
        modality=modality,
        label=_EVIDENCE_LABELS.get(modality, modality),
        text=text,
        summary=summary,
    )


def _customer_value_summary(case: Case) -> str:
    """高价值结论的展示摘要（规格 12.2 customer_value_summary）。"""
    value = (case.case_input_json or {}).get("customer_value") or {}
    if not isinstance(value, dict):
        value = {}
    decision = str(value.get("decision_reason") or "").strip()
    if value.get("is_high_value"):
        return f"高价值客户：{decision}" if decision else "高价值客户"
    parts: list[str] = []
    if "recency_days" in value:
        parts.append(f"R={value['recency_days']}天")
    if "frequency_orders" in value:
        parts.append(f"F={value['frequency_orders']}单")
    if "monetary_total" in value:
        parts.append(f"M={value['monetary_total']}元")
    base = "、".join(parts)
    return f"非高价值客户（{base}）" if base else "非高价值客户"


def _iso_utc(value: datetime) -> str:
    """SQLite 读回时间无 tzinfo 时，按存储约定恢复为 UTC。"""
    return (value if value.tzinfo is not None else value.replace(tzinfo=UTC)).isoformat()


def _review_token(batch_id: str, case_id: str, run: CaseRun) -> str:
    """确定性不透明 review_token：随当前 run_id 变化（规格 12.3；M1-08 同法）。"""
    digest = hashlib.sha256(
        f"psit-review:{batch_id}:{case_id}:{run.run_id}".encode()
    )
    return digest.hexdigest()


def _review_result(
    review: Review, results: list[StageResult]
) -> ReviewResultView:
    """人工确认投影：系统原结果经 review.case_run_id 引用，不在本视图复制。"""
    attribution = _result_by_stage(results, "attribution")
    strategy = _result_by_stage(results, "strategy")
    final_intervention_level = (
        review.final_intervention_level.value
        if review.final_intervention_level is not None
        else None
    )
    final_cause = review.final_cause_json
    final_actions = review.final_actions_json
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


def _current_run(case: Case, runs: dict[int, CaseRun]) -> CaseRun | None:
    """当前 case_run（cases.current_case_run_id 定位）。"""
    if case.current_case_run_id is None or case.current_case_run_id not in runs:
        return None
    return runs[case.current_case_run_id]


class CaseQueryGateway:
    """SQLite 版 CaseQueryGateway：批次/队列/详情投影与 CaseInput 查询。"""

    def __init__(self, *, engine: Engine, formal_root: Path) -> None:
        self.formal_root = Path(formal_root)
        self.repository = CaseQueryRepository(engine, formal_root=formal_root)

    # ---------- 批次 ----------

    def list_batches(
        self, *, limit: int | None = None, offset: int | None = None
    ) -> BatchListView:
        """批次分页列表：imported_at 倒序、batch_id 升序（规格 12.1）。"""
        limit = _required_limit(limit, 20)
        offset = _required_offset(offset)
        batches, total = self.repository.list_batches(limit=limit, offset=offset)
        items = [self._batch_workspace(batch) for batch in batches]
        return BatchListView(items=items, total=total)

    def get_batch(self, batch_id: str) -> BatchWorkspaceView:
        """批次详情投影；批次不存在抛 LookupError（M3 映射 404）。"""
        batch = self.repository.batch_by_batch_id(batch_id)
        if batch is None:
            raise LookupError(f"批次不存在: {batch_id}")
        return self._batch_workspace(batch)

    def _batch_workspace(self, batch: Batch) -> BatchWorkspaceView:
        """批次投影：状态/计数从当前案例 + 当前 case_run 实时聚合（规格 10.3）。"""
        cases = self.repository.cases_of_batch(batch.id)
        source_filename = self.repository.source_filename(batch)
        imported_at = batch.imported_at.isoformat()
        if not cases:
            return BatchWorkspaceView(
                batch_id=batch.batch_id,
                source_filename=source_filename,
                is_mock=True,
                status=BatchStatus.PENDING_ANALYSIS.value,
                case_count=0,
                evidence_count=0,
                analysis_succeeded_count=0,
                error_count=0,
                imported_at=imported_at,
                can_start_analysis=False,
            )
        runs = self.repository.runs_by_ids(
            run_id
            for run_id in (case.current_case_run_id for case in cases)
            if run_id is not None
        )
        counts = self.repository.stage_result_counts(runs)
        has_batch_runs = bool(self.repository.batch_runs_of_batch(batch.id))
        status = _batch_status(cases, runs, counts, has_batch_runs)
        analysis_succeeded = sum(
            1
            for case in cases
            if case.status in (CaseStatus.PENDING_REVIEW, CaseStatus.COMPLETED)
            and _has_complete_package(case, runs, counts)
        )
        error_count = sum(
            1 for case in cases if case.status == CaseStatus.PROCESSING_ERROR
        )
        can_start = (
            not self.repository.active_batch_run_exists()
            and all(case.status == CaseStatus.PENDING_ANALYSIS for case in cases)
        )
        return BatchWorkspaceView(
            batch_id=batch.batch_id,
            source_filename=source_filename,
            is_mock=_is_mock(cases[0]),
            status=status,
            case_count=len(cases),
            evidence_count=self.repository.evidence_count_for_batch(batch.id),
            analysis_succeeded_count=analysis_succeeded,
            error_count=error_count,
            imported_at=imported_at,
            can_start_analysis=can_start,
        )

    # ---------- 案例队列 ----------

    def list_cases(
        self,
        batch_id: str,
        *,
        status: str | None = None,
        intervention_level: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> CaseQueueView:
        """案例队列：固定业务排序 + 单个 status/介入等级筛选 + 分页（规格 12.1）。"""
        limit = _required_limit(limit, 50)
        offset = _required_offset(offset)
        _validate_status_filter(status)
        _validate_level_filter(intervention_level)
        batch = self.repository.batch_by_batch_id(batch_id)
        if batch is None:
            raise LookupError(f"批次不存在: {batch_id}")
        cases = self.repository.cases_of_batch(batch.id)
        runs = self.repository.runs_by_ids(
            run_id
            for run_id in (case.current_case_run_id for case in cases)
            if run_id is not None
        )
        grouped = self.repository.stage_results_of_runs(runs)

        enriched: list[
            tuple[int, object, str, Case, str | None, tuple[bool, bool, bool], list[StageResult]]
        ] = []
        for case in cases:
            level = _case_level(case)
            if status is not None and case.status.value != status:
                continue
            if intervention_level is not None and level != intervention_level:
                continue
            current_run = _current_run(case, runs)
            results = (
                grouped.get(case.current_case_run_id, [])
                if case.current_case_run_id is not None
                else []
            )
            flags = _run_flags(results, current_run)
            enriched.append(
                (
                    _intervention_rank(level),
                    case.imported_at,
                    case.case_id,
                    case,
                    level,
                    flags,
                    results,
                )
            )

        enriched.sort(key=lambda item: (item[0], item[1], item[2]))
        total = len(enriched)
        page = enriched[offset : offset + limit]
        items = [
            CaseQueueItemView(
                case_id=case.case_id,
                customer_display_id=case.customer_display_id,
                is_high_value=case.is_high_value,
                risk_summary=_top_level(results, "risk_summary"),
                intervention_level=level,
                priority_reason=_top_level(results, "priority_reason"),
                status=case.status.value,
                has_evidence_conflict=flags[0],
                has_insufficient_evidence=flags[1],
                has_modality_failure=flags[2],
            )
            for _rank, _imported, _case_id, case, level, flags, results in page
        ]
        return CaseQueueView(items=items, total=total)

    # ---------- 案例详情 ----------

    def get_case_detail(self, batch_id: str, case_id: str) -> CaseDetailView:
        """案例详情：只投影当前 case_run 结果与人工确认结果；首次历史不混用。"""
        batch = self.repository.batch_by_batch_id(batch_id)
        if batch is None:
            raise LookupError(f"批次不存在: {batch_id}")
        case = self.repository.case_of_batch(batch.id, case_id)
        if case is None:
            raise LookupError(f"案例不存在: {batch_id}/{case_id}")

        all_runs = self.repository.case_runs_of_case(case.id)
        runs_by_id = {run.id: run for run in all_runs}
        current_run = _current_run(case, runs_by_id)
        grouped = self.repository.stage_results_of_runs(runs_by_id)
        current_results = (
            grouped.get(case.current_case_run_id, [])
            if case.current_case_run_id is not None
            else []
        )
        perception = _result_by_stage(current_results, "perception")
        attribution = _result_by_stage(current_results, "attribution")
        strategy = _result_by_stage(current_results, "strategy")
        _ = _run_flags(current_results, current_run)

        evidence_rows = self.repository.evidence_of_case(case.id)
        evidence_by_id = {row.evidence_id: row for row in evidence_rows}
        cited_ids = _collect_cited_evidence_ids(current_results, evidence_by_id)
        cited_evidence = [
            _cited_evidence_view(evidence_by_id[evidence_id], perception)
            for evidence_id in cited_ids
        ]

        reviews = self.repository.reviews_of_case(case.id)
        review_result: ReviewResultView | None = None
        if reviews:
            review = reviews[0]
            review_results = grouped.get(review.case_run_id, [])
            review_result = _review_result(review, review_results)

        can_rerun = (
            self.repository.active_case_run_of_case(case.id) is None
            and case.status in (CaseStatus.PENDING_REVIEW, CaseStatus.PROCESSING_ERROR)
        )
        can_review = (
            case.status == CaseStatus.PENDING_REVIEW and case.current_review_id is None
        )
        review_token = (
            _review_token(batch.batch_id, case.case_id, current_run)
            if can_review and current_run is not None
            else None
        )
        processing_error = (
            _processing_error(current_run)
            if case.status == CaseStatus.PROCESSING_ERROR
            else None
        )
        return CaseDetailView(
            batch_id=batch.batch_id,
            case_id=case.case_id,
            customer_display_id=case.customer_display_id,
            is_high_value=case.is_high_value,
            customer_value_summary=_customer_value_summary(case),
            status=case.status.value,
            intervention_level=_case_level(case),
            risk_summary=_top_level(current_results, "risk_summary"),
            primary_cause=(
                attribution.get("primary_cause")
                if attribution is not None
                and isinstance(attribution.get("primary_cause"), dict)
                else None
            ),
            actions=_requires_list(strategy.get("actions")) if strategy is not None else None,
            communication_points=(
                _requires_list(strategy.get("communication_points"))
                if strategy is not None
                else None
            ),
            uncertainty=_requires_list(_top_level(current_results, "uncertainty")),
            missing_evidence=_requires_list(_top_level(current_results, "missing_evidence")),
            cited_evidence=cited_evidence or None,
            is_mock=_is_mock(case),
            review_result=review_result,
            processing_error=processing_error,
            can_rerun=can_rerun,
            can_review=can_review,
            review_token=review_token,
            review_options=build_review_options() if can_review else None,
        )

    # ---------- CaseInput 查询 ----------

    def get_case_input(self, batch_id: str, case_id: str) -> CaseInput | None:
        """返回 CaseInput v1；批次或案例不存在返回 None（不抛异常）。"""
        batch = self.repository.batch_by_batch_id(batch_id)
        if batch is None:
            return None
        case = self.repository.case_of_batch(batch.id, case_id)
        if case is None:
            return None
        return CaseInput.model_validate(case.case_input_json)


__all__ = ["CaseQueryGateway"]
