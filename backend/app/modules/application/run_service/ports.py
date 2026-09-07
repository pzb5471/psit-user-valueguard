"""M3-05 运行服务：调用 M1 RunStore 与 M2 分析引擎的公开端口协议。

只声明 M1/M2 的公开能力，不导入其实现类、ORM 或内部细节；Fake 必须返回
同一类合同对象/异常，不能直接让 M3 走捷径绕过编排。状态决定归 M3、数据
原子写入归 M1、分析职责归 M2（规格 8/9.1/10.2）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from app.contracts.analysis import (
    AnalysisEventSink,
    AnalysisOutcome,
    AnalysisRequest,
    CaseInputV1Protocol,
)
from app.modules.data.queries.views import (
    BatchWorkspaceView as DataBatchWorkspaceView,
)
from app.modules.data.queries.views import (
    CaseDetailView as DataCaseDetailView,
)
from app.modules.data.queries.views import (
    CaseQueueView as DataCaseQueueView,
)
from app.modules.data.run_store.types import (
    BatchRunView,
    CaseRunView,
    FailureResult,
    ModelAttemptInput,
    PublishResult,
    RecoverySummary,
    StageResultInput,
)


class AnalysisEnginePort(Protocol):
    """M2 AnalysisEngine 的唯一同步阻塞入口（规格 9.1）。"""

    def analyze_case(
        self, request: AnalysisRequest, event_sink: AnalysisEventSink
    ) -> AnalysisOutcome: ...


class RunStorePort(Protocol):
    """M1 RunStore 的运行历史写端口（规格第 8 节；短事务原子写入）。"""

    def create_batch_run(
        self,
        *,
        batch_id: str,
        run_id: str,
        total_case_count: int,
        batch_status: object = ...,
        started_at: datetime | None = None,
    ) -> BatchRunView: ...

    def create_case_run(
        self,
        *,
        batch_id: str,
        case_id: str,
        run_id: str,
        trigger_type: object,
        batch_run_id: str | None = None,
        case_status: object = ...,
        run_status: object = ...,
        started_at: datetime | None = None,
    ) -> CaseRunView: ...

    def record_stage_started(
        self,
        *,
        case_run_id: int,
        stage_name: str,
        status: object,
        occurred_at: datetime | None = None,
    ) -> None: ...

    def record_model_attempt(
        self, *, case_run_id: int, attempt: ModelAttemptInput
    ) -> None: ...

    def record_stage_result(
        self, *, case_run_id: int, stage: StageResultInput, occurred_at: datetime | None = None
    ) -> None: ...

    def record_failure(
        self,
        *,
        case_run_id: int,
        error_code: str,
        error_stage: str,
        error_detail_json: dict | None = None,
        case_status: object = ...,
        run_status: object = ...,
        occurred_at: datetime | None = None,
    ) -> FailureResult: ...

    def publish_complete_result(
        self,
        *,
        case_run_id: int,
        final_stage: StageResultInput,
        system_intervention_level: str | None = None,
        case_status: object = ...,
        run_status: object = ...,
        occurred_at: datetime | None = None,
    ) -> PublishResult: ...

    def finish_batch_run(
        self, *, batch_run_id: int, status: object, finished_at: datetime | None = None
    ) -> BatchRunView: ...

    def recover_interrupted(self, *, now: datetime | None = None) -> RecoverySummary: ...


class RunQueryPort(Protocol):
    """M3 查询运行输入：拿批次投影、案例清单与 CaseInput。"""

    def get_batch(self, batch_id: str) -> DataBatchWorkspaceView: ...

    def list_cases(
        self, batch_id: str, *, limit: int | None = None, offset: int | None = None
    ) -> DataCaseQueueView: ...

    def get_case_detail(self, batch_id: str, case_id: str) -> DataCaseDetailView: ...

    def get_case_input(self, batch_id: str, case_id: str) -> CaseInputV1Protocol | None: ...
