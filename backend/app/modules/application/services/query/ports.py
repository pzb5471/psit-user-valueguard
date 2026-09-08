"""M3-04 调用 M1 的公开数据端口协议。

这里只声明 M1 的公开能力，不导入 M1 实现类、ORM、Session 或仓库对象。
M1 的 Pydantic 投影/文件流作为跨模块合同对象传递；测试 Fake 必须返回
同一类合同对象，不能直接返回 M3 API DTO 绕过转换层。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import BinaryIO, Protocol

from app.modules.data.evidence.gateway import EvidenceContent
from app.modules.data.importing.gateway import ImportResult
from app.modules.data.queries.views import (
    BatchListView as DataBatchListView,
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


class BatchImportPort(Protocol):
    """M1 BatchImportGateway 的公开端口。"""

    def import_zip(
        self,
        source: bytes | BinaryIO,
        *,
        source_filename: str = "upload.zip",
        content_length: int | None = None,
        trace_id: str | None = None,
    ) -> ImportResult: ...


class CaseQueryPort(Protocol):
    """M1 CaseQueryGateway 的公开查询端口。"""

    def list_batches(
        self, *, limit: int | None = None, offset: int | None = None
    ) -> DataBatchListView: ...

    def get_batch(self, batch_id: str) -> DataBatchWorkspaceView: ...

    def list_cases(
        self,
        batch_id: str,
        *,
        status: str | None = None,
        intervention_level: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> DataCaseQueueView: ...

    def get_case_detail(self, batch_id: str, case_id: str) -> DataCaseDetailView: ...


class EvidencePort(Protocol):
    """M1 EvidenceGateway 的公开证据文件流端口。"""

    def get_evidence_content(
        self, batch_id: str, case_id: str, evidence_id: str
    ) -> EvidenceContent: ...


@dataclass(frozen=True, slots=True)
class M1Ports:
    """M3-04 服务所需的三个 M1 公开端口；只通过显式注入装配。"""

    importer: BatchImportPort
    query: CaseQueryPort
    evidence: EvidencePort
