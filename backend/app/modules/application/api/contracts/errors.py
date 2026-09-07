"""统一错误合同（技术实施规格 12.4；ADR 0026、0072）。

所有 JSON 错误统一为 BusinessError 结构；FastAPI 默认 422 与未处理 500
由 ``install_error_boundary`` 转换为同一结构，页面不得看到异常类名、
堆栈、密钥、SDK 原始错误、本机路径或供应商响应。
"""

from __future__ import annotations

from enum import StrEnum
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "ApiErrorCode",
    "BusinessError",
    "CaseProcessingErrorCode",
    "ERROR_HTTP_STATUS",
    "ProcessingErrorStage",
    "install_error_boundary",
]


class ApiErrorCode(StrEnum):
    """v1 对外错误编号（规格 12.4 错误表，固定十五个）。"""

    INVALID_ZIP = "INVALID_ZIP"
    INPUT_CONTRACT_INVALID = "INPUT_CONTRACT_INVALID"
    ANSWER_LEAKAGE_DETECTED = "ANSWER_LEAKAGE_DETECTED"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    BATCH_ID_CONFLICT = "BATCH_ID_CONFLICT"
    ACTIVE_BATCH_EXISTS = "ACTIVE_BATCH_EXISTS"
    ACTIVE_CASE_RUN_EXISTS = "ACTIVE_CASE_RUN_EXISTS"
    CASE_NOT_RERUNNABLE = "CASE_NOT_RERUNNABLE"
    CASE_ALREADY_COMPLETED = "CASE_ALREADY_COMPLETED"
    STALE_CASE_RESULT = "STALE_CASE_RESULT"
    UPLOAD_TOO_LARGE = "UPLOAD_TOO_LARGE"
    UNSUPPORTED_MEDIA_TYPE = "UNSUPPORTED_MEDIA_TYPE"
    REQUEST_VALIDATION_FAILED = "REQUEST_VALIDATION_FAILED"
    ANALYSIS_UNAVAILABLE = "ANALYSIS_UNAVAILABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class CaseProcessingErrorCode(StrEnum):
    """案例异步处理错误编号（规格 12.4），通过 processing_error 业务化展示。"""

    EVIDENCE_READ_FAILED = "EVIDENCE_READ_FAILED"
    EVIDENCE_MEDIA_INVALID = "EVIDENCE_MEDIA_INVALID"
    MODEL_AUTH_FAILED = "MODEL_AUTH_FAILED"
    MODEL_TIMEOUT = "MODEL_TIMEOUT"
    MODEL_RATE_LIMITED = "MODEL_RATE_LIMITED"
    MODEL_RESPONSE_INVALID = "MODEL_RESPONSE_INVALID"
    MODEL_ATTEMPTS_EXHAUSTED = "MODEL_ATTEMPTS_EXHAUSTED"
    RESULT_PERSISTENCE_FAILED = "RESULT_PERSISTENCE_FAILED"
    APP_INTERRUPTED = "APP_INTERRUPTED"
    UNEXPECTED_PROCESSING_ERROR = "UNEXPECTED_PROCESSING_ERROR"


class ProcessingErrorStage(StrEnum):
    """业务化阶段白名单（规格 12.2）；不把感知、归因、策略等内部阶段透传给运营人员。"""

    INPUT_PREPARATION = "INPUT_PREPARATION"
    EVIDENCE_PROCESSING = "EVIDENCE_PROCESSING"
    AI_ANALYSIS = "AI_ANALYSIS"
    RESULT_PERSISTENCE = "RESULT_PERSISTENCE"
    APP_RECOVERY = "APP_RECOVERY"


#: 错误编号到 HTTP 状态码的冻结映射（规格 12.4 错误表）。
ERROR_HTTP_STATUS: dict[ApiErrorCode, int] = {
    ApiErrorCode.INVALID_ZIP: 400,
    ApiErrorCode.INPUT_CONTRACT_INVALID: 400,
    ApiErrorCode.ANSWER_LEAKAGE_DETECTED: 400,
    ApiErrorCode.RESOURCE_NOT_FOUND: 404,
    ApiErrorCode.BATCH_ID_CONFLICT: 409,
    ApiErrorCode.ACTIVE_BATCH_EXISTS: 409,
    ApiErrorCode.ACTIVE_CASE_RUN_EXISTS: 409,
    ApiErrorCode.CASE_NOT_RERUNNABLE: 409,
    ApiErrorCode.CASE_ALREADY_COMPLETED: 409,
    ApiErrorCode.STALE_CASE_RESULT: 409,
    ApiErrorCode.UPLOAD_TOO_LARGE: 413,
    ApiErrorCode.UNSUPPORTED_MEDIA_TYPE: 415,
    ApiErrorCode.REQUEST_VALIDATION_FAILED: 422,
    ApiErrorCode.ANALYSIS_UNAVAILABLE: 503,
    ApiErrorCode.INTERNAL_ERROR: 500,
}


class BusinessError(BaseModel):
    """统一 JSON 错误结构（规格 12.4）。"""

    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    object_type: str
    object_id: str | None = None
    stage: ProcessingErrorStage
    next_action: str
    trace_id: str = Field(default_factory=lambda: uuid4().hex, min_length=1)


def _boundary_error(
    code: ApiErrorCode,
    message: str,
    stage: ProcessingErrorStage,
    next_action: str,
) -> JSONResponse:
    error = BusinessError(
        code=code.value,
        message=message,
        object_type="request",
        stage=stage,
        next_action=next_action,
    )
    return JSONResponse(
        status_code=ERROR_HTTP_STATUS[code], content=error.model_dump()
    )


def install_error_boundary(app: FastAPI) -> None:
    """把 FastAPI 默认 422 与未处理 500 转换为 BusinessError（规格 12.4）。

    具体业务错误由后续 Task（M3-04 至 M3-07）的路由按同一结构显式抛出；
    本边界只兜住框架默认形态，不透传异常类名或堆栈。
    """

    @app.exception_handler(RequestValidationError)
    async def _request_validation_failed(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return _boundary_error(
            ApiErrorCode.REQUEST_VALIDATION_FAILED,
            "请求字段、类型或枚举不合格",
            ProcessingErrorStage.INPUT_PREPARATION,
            "请检查请求参数后重试",
        )

    @app.exception_handler(Exception)
    async def _internal_error(request: Request, exc: Exception) -> JSONResponse:
        return _boundary_error(
            ApiErrorCode.INTERNAL_ERROR,
            "服务内部错误，请稍后重试",
            ProcessingErrorStage.APP_RECOVERY,
            "请稍后重试；如持续失败请联系技术支持",
        )
