"""M3-04 测试用 Fake M1 端口。

Fake 返回 M1 的公开合同对象（ImportResult、M1 投影 DTO、EvidenceContent），
M3 服务层仍走完整转换，不直接返回 M3 API DTO，避免 Fake 绕过接口合同。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, BinaryIO

from app.modules.data.evidence.errors import EvidenceNotFoundError
from app.modules.data.evidence.gateway import EvidenceContent
from app.modules.data.importing.errors import (
    ImportRejectionCode,
    ImportStage,
    RejectionInfo,
)
from app.modules.data.importing.gateway import ImportResult
from app.modules.data.queries.views import (
    BatchListView,
    BatchWorkspaceView,
    CaseDetailView,
    CaseQueueItemView,
    CaseQueueView,
    ReviewOptionsView,
    build_review_options,
)

IMPORTED_AT = "2026-09-07T08:00:00+00:00"


def make_workspace(
    batch_id: str = "b1",
    *,
    status: str = "PENDING_ANALYSIS",
    case_count: int = 0,
    evidence_count: int = 0,
    can_start: bool = True,
) -> BatchWorkspaceView:
    return BatchWorkspaceView(
        batch_id=batch_id,
        source_filename="mvp.zip",
        is_mock=True,
        status=status,
        case_count=case_count,
        evidence_count=evidence_count,
        analysis_succeeded_count=0,
        error_count=0,
        imported_at=IMPORTED_AT,
        can_start_analysis=can_start,
        analysis_unavailable_message=None,
    )


def make_queue_item(
    case_id: str,
    *,
    status: str = "PENDING_ANALYSIS",
    level: str | None = None,
) -> CaseQueueItemView:
    return CaseQueueItemView(
        case_id=case_id,
        customer_display_id=f"客户-{case_id}",
        is_high_value=True,
        risk_summary="高价值风险待处理",
        intervention_level=level,
        priority_reason=None,
        status=status,
        has_evidence_conflict=False,
        has_insufficient_evidence=False,
        has_modality_failure=False,
    )


@dataclass
class FakeImporter:
    """可配置的 Fake BatchImportPort：按包内容字节决定成功/重复/拒绝。"""

    duplicate_bytes: bytes | None = None
    reject_code: ImportRejectionCode | None = None
    calls: list[tuple[bytes, str, int | None, str | None]] = field(default_factory=list)

    def import_zip(
        self,
        source: bytes | BinaryIO,
        *,
        source_filename: str = "upload.zip",
        content_length: int | None = None,
        trace_id: str | None = None,
    ) -> ImportResult:
        raw = source if isinstance(source, bytes) else source.read()
        self.calls.append((raw, source_filename, content_length, trace_id))
        if self.duplicate_bytes is not None and raw == self.duplicate_bytes:
            return ImportResult(
                ok=True,
                source_filename=source_filename,
                batch_id="b1",
                status="PENDING_ANALYSIS",
                is_mock=True,
                case_count=2,
                evidence_count=3,
                imported=True,
                returned_existing=True,
                trace_id=trace_id or "",
            )
        if self.reject_code is not None:
            return ImportResult(
                ok=False,
                source_filename=source_filename,
                rejections=(
                    RejectionInfo(
                        code=self.reject_code,
                        message="上传包不合格",
                        object_type="package",
                        object_id="",
                        stage=ImportStage.IMPORT,
                        next_action="请检查后重试",
                        trace_id=trace_id or "",
                    ),
                ),
                trace_id=trace_id or "",
            )
        return ImportResult(
            ok=True,
            source_filename=source_filename,
            batch_id="b1",
            status="PENDING_ANALYSIS",
            is_mock=True,
            case_count=2,
            evidence_count=3,
            imported=True,
            returned_existing=False,
            trace_id=trace_id or "",
        )


@dataclass
class FakeQuery:
    """Fake CaseQueryPort：内存投影 + 调用记录（分页/筛选参数可断言）。"""

    batches: list[BatchWorkspaceView] = field(default_factory=list)
    queue: list[CaseQueueItemView] = field(default_factory=list)
    detail: CaseDetailView | None = None
    missing_batch: bool = False
    last_list_batches_args: tuple[int | None, int | None] | None = None
    last_list_cases_args: tuple[str | None, str | None, int | None, int | None] | None = None

    def list_batches(self, *, limit=None, offset=None) -> BatchListView:
        self.last_list_batches_args = (limit, offset)
        items = self.batches[offset : offset + limit] if limit is not None else self.batches
        return BatchListView(items=items, total=len(self.batches))

    def get_batch(self, batch_id: str) -> BatchWorkspaceView:
        if self.missing_batch:
            raise LookupError(f"批次不存在: {batch_id}")
        for batch in self.batches:
            if batch.batch_id == batch_id:
                return batch
        raise LookupError(f"批次不存在: {batch_id}")

    def list_cases(
        self,
        batch_id: str,
        *,
        status: str | None = None,
        intervention_level: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> CaseQueueView:
        if self.missing_batch:
            raise LookupError(f"批次不存在: {batch_id}")
        self.last_list_cases_args = (status, intervention_level, limit, offset)
        filtered = [
            item
            for item in self.queue
            if (status is None or item.status == status)
            and (intervention_level is None or item.intervention_level == intervention_level)
        ]
        start = 0 if offset is None else offset
        page = filtered[start : start + limit] if limit is not None else filtered
        return CaseQueueView(items=page, total=len(filtered))

    def get_case_detail(self, batch_id: str, case_id: str) -> CaseDetailView:
        detail = self.detail
        if detail is None or detail.batch_id != batch_id or detail.case_id != case_id:
            raise LookupError(f"案例不存在: {batch_id}/{case_id}")
        return detail


@dataclass
class FakeEvidence:
    """Fake EvidencePort：按证据 id 返回字节流或抛错误。"""

    content: EvidenceContent | None = None
    not_found: bool = False
    unsupported: bool = False
    calls: list[tuple[str, str, str]] = field(default_factory=list)

    def get_evidence_content(
        self, batch_id: str, case_id: str, evidence_id: str
    ) -> EvidenceContent:
        self.calls.append((batch_id, case_id, evidence_id))
        if self.not_found:
            raise EvidenceNotFoundError(object_type="evidence", object_id=evidence_id)
        if self.unsupported:
            from app.modules.data.evidence.errors import UnsupportedMediaTypeError

            raise UnsupportedMediaTypeError(object_id=evidence_id)
        if self.content is None:
            raise EvidenceNotFoundError(object_type="evidence", object_id=evidence_id)
        return self.content


def make_detail(**overrides: Any) -> CaseDetailView:
    """构造一个可复用最小案例详情投影（PENDING_ANALYSIS，无运行结果）。"""
    base: dict[str, Any] = {
        "batch_id": "b1",
        "case_id": "c1",
        "customer_display_id": "客户-c1",
        "is_high_value": True,
        "customer_value_summary": "高价值客户：测试",
        "status": "PENDING_ANALYSIS",
        "is_mock": True,
        "can_rerun": False,
        "can_review": False,
    }
    base.update(overrides)
    return CaseDetailView(**base)


def make_review_options() -> ReviewOptionsView:
    return build_review_options()


def hash_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()
