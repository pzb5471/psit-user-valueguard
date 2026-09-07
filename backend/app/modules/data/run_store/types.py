"""M1-07：RunStore 输入与输出 DTO（技术实施规格 8/9.2/10.2—10.5）。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class ModelAttemptInput:
    """一次模型调用的追加记录（规格 9.2 保存规则）。

    保存模型名、Prompt 版本、请求清单、尝试序号、状态、响应或错误、起止时间、
    耗时与供应商实际返回的可用 Token 计数；供应商完整响应不重复保存到日志
    （规格 9.2：不重复保存供应商完整响应）。
    """

    call_id: str
    stage_name: str
    attempt_no: int
    model_name: str
    prompt_version: str
    request_manifest_json: dict[str, Any]
    status: str
    response_json: dict[str, Any] | None = None
    error_json: dict[str, Any] | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    latency_ms: int | None = None
    prompt_token_count: int | None = None
    completion_token_count: int | None = None
    total_token_count: int | None = None


@dataclass(frozen=True, slots=True)
class StageResultInput:
    """一份通过合同与程序规则校验的阶段最终合格结果（规格 11.1/11.2）。"""

    stage_name: str
    contract_version: str
    result_json: dict[str, Any]
    result_sha256: str


@dataclass(frozen=True, slots=True)
class BatchRunView:
    """批次首次批量分析运行投影（内部 id 供 M3 编排，HTTP 不输出整数主键）。"""

    id: int
    run_id: str
    batch_id: str
    status: str
    total_case_count: int
    analysis_succeeded_count: int
    error_count: int
    started_at: str
    finished_at: str | None


@dataclass(frozen=True, slots=True)
class CaseRunView:
    """案例运行投影：id 为内部 case_run_id（M3 用于 AnalysisRequest，规格 9.1）。"""

    id: int
    run_id: str
    batch_id: str
    case_id: str
    trigger_type: str
    status: str
    current_stage: str | None
    previous_case_run_id: int | None
    batch_run_id: int | None
    started_at: str
    finished_at: str | None


@dataclass(frozen=True, slots=True)
class PublishResult:
    """完整决策包原子发布结果（规格 10.4），含发布后的批次当前状态与计数。"""

    case_run_id: int
    run_id: str
    batch_id: str
    case_id: str
    batch_status: str
    analysis_succeeded_count: int
    error_count: int


@dataclass(frozen=True, slots=True)
class FailureResult:
    """技术失败记录结果（规格 10.2/10.3），含记录后的批次当前状态与计数。"""

    case_run_id: int
    run_id: str
    batch_id: str
    case_id: str
    error_code: str
    batch_status: str
    analysis_succeeded_count: int
    error_count: int


@dataclass(frozen=True, slots=True)
class RecoverySummary:
    """启动恢复检查摘要（规格 10.5），全部为零表示没有需要恢复的活动运行。"""

    interrupted_case_runs: int
    interrupted_batch_runs: int
    error_cases: int
    affected_batches: int
