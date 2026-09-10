"""M3-04 业务服务：导入、查询与证据，只依赖 M1 公开端口（规格第 8 节）。

服务层决定业务错误映射（M1 拒绝码/异常 → 稳定 ApiErrorCode），并调用
mapper 把 M1 投影转换为对外 API DTO。M1 端口的真实实现由 M3-08 接线装配，
本层与路由只面对端口协议；测试通过 Fake 端口注入。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import BinaryIO

from app.modules.application.api.contracts.errors import ApiErrorCode
from app.modules.application.api.contracts.views import (
    BatchListView,
    BatchWorkspaceView,
    CaseDetailView,
    CaseQueueView,
)
from app.modules.application.services.query import mapper
from app.modules.application.services.query.errors import ServiceError
from app.modules.application.services.query.ports import M1Ports
from app.modules.data.evidence.errors import (
    EvidenceGatewayError,
    EvidenceNotFoundError,
)
from app.modules.data.evidence.gateway import EvidenceContent
from app.modules.data.importing.errors import ImportRejectionCode
from app.modules.data.importing.gateway import ImportResult

#: M1 导入拒绝码 → 对外 ApiErrorCode（规格 12.4 错误表）。
_IMPORT_REJECTION_MAP: dict[ImportRejectionCode, ApiErrorCode] = {
    ImportRejectionCode.INVALID_ZIP: ApiErrorCode.INVALID_ZIP,
    ImportRejectionCode.INPUT_CONTRACT_INVALID: ApiErrorCode.INPUT_CONTRACT_INVALID,
    ImportRejectionCode.ANSWER_LEAKAGE_DETECTED: ApiErrorCode.ANSWER_LEAKAGE_DETECTED,
    ImportRejectionCode.UNSUPPORTED_MEDIA_TYPE: ApiErrorCode.UNSUPPORTED_MEDIA_TYPE,
    ImportRejectionCode.UPLOAD_TOO_LARGE: ApiErrorCode.UPLOAD_TOO_LARGE,
    ImportRejectionCode.BATCH_ID_CONFLICT: ApiErrorCode.BATCH_ID_CONFLICT,
    ImportRejectionCode.INTERNAL_ERROR: ApiErrorCode.INTERNAL_ERROR,
}


def _import_error(result: ImportResult) -> ServiceError:
    rejection = result.rejections[0] if result.rejections else None
    if rejection is None:
        return ServiceError(
            ApiErrorCode.INTERNAL_ERROR,
            "导入未返回结果，请稍后重试",
        )
    return ServiceError(
        code=_IMPORT_REJECTION_MAP.get(rejection.code, ApiErrorCode.INTERNAL_ERROR),
        message=rejection.message,
        object_type=rejection.object_type,
        object_id=rejection.object_id,
        next_action=rejection.next_action,
    )


@dataclass(frozen=True, slots=True)
class ImportOutcome:
    """导入响应：是否命中已有批次 + 对外批次视图。"""

    returned_existing: bool
    workspace: BatchWorkspaceView


class ApplicationServices:
    """M3 面向 M1 端口的数据服务；以显式端口注入构造（无可变全局装配）。"""

    def __init__(
        self,
        ports: M1Ports,
        *,
        analysis_available: bool = True,
        analysis_unavailable_message: str | None = None,
    ) -> None:
        self.ports = ports
        self._analysis_available = analysis_available
        self._analysis_unavailable_message = analysis_unavailable_message

    def _apply_analysis_availability(
        self, view: BatchWorkspaceView
    ) -> BatchWorkspaceView:
        if self._analysis_available:
            return view
        return view.model_copy(
            update={
                "can_start_analysis": False,
                "analysis_unavailable_message": self._analysis_unavailable_message,
            }
        )

    # ---------- 导入 ----------

    def import_batch(
        self,
        source: bytes | BinaryIO,
        *,
        source_filename: str,
        content_length: int | None,
        trace_id: str,
    ) -> ImportOutcome:
        result = self.ports.importer.import_zip(
            source,
            source_filename=source_filename,
            content_length=content_length,
            trace_id=trace_id,
        )
        if not result.ok:
            raise _import_error(result)
        assert result.batch_id is not None
        workspace = self.ports.query.get_batch(result.batch_id)
        return ImportOutcome(
            returned_existing=result.returned_existing,
            workspace=self._apply_analysis_availability(
                mapper.to_batch_workspace(workspace)
            ),
        )

    # ---------- 查询 ----------

    def list_batches(self, *, limit: int, offset: int) -> BatchListView:
        view = mapper.to_batch_list(
            self.ports.query.list_batches(limit=limit, offset=offset)
        )
        return view.model_copy(
            update={
                "items": [
                    self._apply_analysis_availability(item) for item in view.items
                ]
            }
        )

    def get_batch(self, batch_id: str) -> BatchWorkspaceView:
        try:
            view = self.ports.query.get_batch(batch_id)
        except LookupError:
            raise ServiceError(
                ApiErrorCode.RESOURCE_NOT_FOUND,
                f"批次不存在：{batch_id}",
                object_type="batch",
                object_id=batch_id,
            ) from None
        return self._apply_analysis_availability(mapper.to_batch_workspace(view))

    def list_cases(
        self,
        batch_id: str,
        *,
        status: str | None,
        intervention_level: str | None,
        limit: int,
        offset: int,
    ) -> CaseQueueView:
        try:
            view = self.ports.query.list_cases(
                batch_id,
                status=status,
                intervention_level=intervention_level,
                limit=limit,
                offset=offset,
            )
        except LookupError:
            raise ServiceError(
                ApiErrorCode.RESOURCE_NOT_FOUND,
                f"批次不存在：{batch_id}",
                object_type="batch",
                object_id=batch_id,
            ) from None
        except ValueError as error:
            raise ServiceError(
                ApiErrorCode.REQUEST_VALIDATION_FAILED,
                str(error),
            ) from None
        return mapper.to_case_queue(view)

    def get_case_detail(self, batch_id: str, case_id: str) -> CaseDetailView:
        try:
            view = self.ports.query.get_case_detail(batch_id, case_id)
        except LookupError as error:
            message = str(error)
            is_case = "案例不存在" in message
            raise ServiceError(
                ApiErrorCode.RESOURCE_NOT_FOUND,
                message,
                object_type="case" if is_case else "batch",
                object_id=case_id if is_case else batch_id,
            ) from None
        return mapper.to_case_detail(view)

    # ---------- 证据 ----------

    def get_evidence_content(
        self, batch_id: str, case_id: str, evidence_id: str
    ) -> EvidenceContent:
        try:
            return self.ports.evidence.get_evidence_content(
                batch_id, case_id, evidence_id
            )
        except EvidenceNotFoundError as error:
            raise ServiceError(
                ApiErrorCode.RESOURCE_NOT_FOUND,
                error.message,
                object_type=error.object_type,
                object_id=error.object_id,
                next_action=error.next_action,
            ) from None
        except EvidenceGatewayError as error:
            raise ServiceError(
                ApiErrorCode.UNSUPPORTED_MEDIA_TYPE,
                error.message,
                object_type=error.object_type,
                object_id=error.object_id,
                next_action=error.next_action,
            ) from None
