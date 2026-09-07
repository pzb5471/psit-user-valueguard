"""HTTP API v1 路由签名与 OpenAPI 真源（技术实施规格 12 节；M3-03/04）。

方法、路径、参数、成功码、允许状态码与请求/响应模型由 M3-03 冻结；
M3-04 把导入、查询、证据三个数据端口接进路由处理器（其余三个业务接口
分别由 M3-05/06/07 落地，M3-08 接 RunStore/ReviewStore）。健康路由由
M3-02 的 ``register_health`` 提供。

处理器通过依赖注入取得 M3 服务层（``ApplicationServices``，依赖 M1 公开
端口）；服务层把 M1 的拒绝/异常映射为稳定 ``ApiErrorCode``，路由据此构造
BusinessError 响应，不透传 M1 异常类、ORM 或供应商细节。
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    File,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
)
from pydantic import Field

from app.modules.application.api.contracts.errors import (
    ERROR_HTTP_STATUS,
    ApiErrorCode,
    BusinessError,
    install_error_boundary,
)
from app.modules.application.api.contracts.reviews import ReviewRequest
from app.modules.application.api.contracts.views import (
    BatchListView,
    BatchWorkspaceView,
    CaseDetailView,
    CaseQueueView,
    ReviewResultView,
)
from app.modules.application.app_factory.health import register_health
from app.modules.application.config.settings import Settings
from app.modules.application.run_service import RunService
from app.modules.application.services.query import ApplicationServices, ServiceError

__all__ = ["api_router", "create_contract_app"]

#: 错误编号的一行业务说明（规格 12.4 错误表"使用条件"列）。
_ERROR_DESCRIPTIONS: dict[ApiErrorCode, str] = {
    ApiErrorCode.INVALID_ZIP: "ZIP 结构、路径、清单、校验值或内容关系不合格",
    ApiErrorCode.INPUT_CONTRACT_INVALID: "CaseInput、证据来源或案例关系不满足运行合同",
    ApiErrorCode.ANSWER_LEAKAGE_DETECTED: "运行包发现答案或答案性质字段",
    ApiErrorCode.RESOURCE_NOT_FOUND: "批次、案例或证据不存在",
    ApiErrorCode.BATCH_ID_CONFLICT: "相同 batch_id 对应不同包内容",
    ApiErrorCode.ACTIVE_BATCH_EXISTS: "已有首次批量分析正在运行",
    ApiErrorCode.ACTIVE_CASE_RUN_EXISTS: "同一案例已有活动运行",
    ApiErrorCode.CASE_NOT_RERUNNABLE: "当前案例状态不允许重跑",
    ApiErrorCode.CASE_ALREADY_COMPLETED: "已完成案例收到新的审核或重跑请求",
    ApiErrorCode.STALE_CASE_RESULT: "review_token 不再对应当前结果",
    ApiErrorCode.UPLOAD_TOO_LARGE: "ZIP 超过冻结的上传上限",
    ApiErrorCode.UNSUPPORTED_MEDIA_TYPE: "上传或证据媒体类型不受支持",
    ApiErrorCode.REQUEST_VALIDATION_FAILED: "HTTP 字段、联合请求、类型或枚举不合格",
    ApiErrorCode.ANALYSIS_UNAVAILABLE: "缺密钥、模型健康检查失败或应用正在正常关闭",
    ApiErrorCode.INTERNAL_ERROR: "未预期内部异常",
}


def _error_responses(*codes: ApiErrorCode) -> dict[int | str, dict[str, Any]]:
    """按冻结映射生成 BusinessError 响应声明；状态码必须落在 HTTP 白名单内。"""
    responses: dict[int | str, dict[str, Any]] = {}
    for code in codes:
        status = ERROR_HTTP_STATUS[code]
        responses[status] = {
            "model": BusinessError,
            "description": f"{code.value}：{_ERROR_DESCRIPTIONS[code]}",
        }
    return responses


def _service_response_error(error: ServiceError) -> HTTPException:
    """把服务层稳定错误信号构造为 BusinessError 响应（规格 12.4）。"""
    body = BusinessError(
        code=error.code.value,
        message=error.message,
        object_type=error.object_type,
        object_id=error.object_id or None,
        stage=error.stage,
        next_action=error.next_action,
    )
    return HTTPException(
        status_code=ERROR_HTTP_STATUS[error.code], detail=body.model_dump()
    )


def get_services(request: Request) -> ApplicationServices | None:
    """从应用状态取 M3 服务层；未装配（M3-08 前）返回 None 由处理器兜底。"""
    return getattr(request.app.state, "services", None)


def get_run_service(request: Request) -> RunService | None:
    """从应用状态取 M3 运行服务；未装配（M3-08 前）返回 None 由处理器兜底。"""
    return getattr(request.app.state, "run_service", None)


def _require_services(
    services: ApplicationServices | None,
) -> ApplicationServices:
    if services is None:
        raise _service_response_error(
            ServiceError(
                ApiErrorCode.INTERNAL_ERROR,
                "服务尚未装配，请稍后重试",
                next_action="检查应用装配后重试",
            )
        )
    return services


api_router = APIRouter(prefix="/api/v1")

LimitParam = Annotated[int, Query(ge=1, le=100)]
OffsetParam = Annotated[int, Query(ge=0)]


@api_router.post(
    "/batches",
    status_code=201,
    response_model=BatchWorkspaceView,
    response_model_exclude_none=True,
    responses={
        200: {"model": BatchWorkspaceView, "description": "重复包幂等命中"},
        **_error_responses(
            ApiErrorCode.INVALID_ZIP,
            ApiErrorCode.INPUT_CONTRACT_INVALID,
            ApiErrorCode.ANSWER_LEAKAGE_DETECTED,
            ApiErrorCode.BATCH_ID_CONFLICT,
            ApiErrorCode.ACTIVE_BATCH_EXISTS,
            ApiErrorCode.UPLOAD_TOO_LARGE,
            ApiErrorCode.UNSUPPORTED_MEDIA_TYPE,
            ApiErrorCode.REQUEST_VALIDATION_FAILED,
            ApiErrorCode.INTERNAL_ERROR,
        ),
    },
)
async def create_batch(
    file: Annotated[UploadFile, File(description="标准 ZIP 运行包")],
    response: Response,
    services: ApplicationServices | None = Depends(get_services),
) -> BatchWorkspaceView:
    """上传一个标准 ZIP 新建批次；重复包 200 幂等命中（M3-04）。"""
    svc = _require_services(services)
    raw = await file.read()
    try:
        outcome = svc.import_batch(
            raw,
            source_filename=file.filename or "upload.zip",
            content_length=file.size,
            trace_id=uuid.uuid4().hex,
        )
    except ServiceError as error:
        raise _service_response_error(error) from None
    response.status_code = 200 if outcome.returned_existing else 201
    return outcome.workspace


@api_router.get(
    "/batches",
    response_model=BatchListView,
    response_model_exclude_none=True,
    responses=_error_responses(
        ApiErrorCode.REQUEST_VALIDATION_FAILED, ApiErrorCode.INTERNAL_ERROR
    ),
)
async def list_batches(
    limit: LimitParam = 20,
    offset: OffsetParam = 0,
    services: ApplicationServices | None = Depends(get_services),
) -> BatchListView:
    """按 imported_at 倒序、batch_id 稳定排序列出批次（M3-04）。"""
    svc = _require_services(services)
    try:
        return svc.list_batches(limit=limit, offset=offset)
    except ServiceError as error:
        raise _service_response_error(error) from None


@api_router.get(
    "/batches/{batch_id}",
    response_model=BatchWorkspaceView,
    response_model_exclude_none=True,
    responses=_error_responses(
        ApiErrorCode.RESOURCE_NOT_FOUND,
        ApiErrorCode.REQUEST_VALIDATION_FAILED,
        ApiErrorCode.INTERNAL_ERROR,
    ),
)
async def get_batch(
    batch_id: str,
    services: ApplicationServices | None = Depends(get_services),
) -> BatchWorkspaceView:
    """读取单个批次工作台视图（M3-04）。"""
    svc = _require_services(services)
    try:
        return svc.get_batch(batch_id)
    except ServiceError as error:
        raise _service_response_error(error) from None


@api_router.post(
    "/batches/{batch_id}/runs",
    status_code=202,
    response_model=BatchWorkspaceView,
    response_model_exclude_none=True,
    responses=_error_responses(
        ApiErrorCode.RESOURCE_NOT_FOUND,
        ApiErrorCode.ACTIVE_BATCH_EXISTS,
        ApiErrorCode.ANALYSIS_UNAVAILABLE,
        ApiErrorCode.REQUEST_VALIDATION_FAILED,
        ApiErrorCode.INTERNAL_ERROR,
    ),
)
async def start_batch_run(
    batch_id: str,
    run_service: RunService | None = Depends(get_run_service),
) -> BatchWorkspaceView:
    """开始首次批量分析；无请求体，缺密钥时 503（M3-05）。"""
    if run_service is None:
        raise _service_response_error(
            ServiceError(
                ApiErrorCode.INTERNAL_ERROR,
                "运行服务尚未装配，请稍后重试",
                next_action="检查应用装配后重试",
            )
        )
    try:
        return run_service.start_batch_run(batch_id)
    except ServiceError as error:
        raise _service_response_error(error) from None


@api_router.get(
    "/batches/{batch_id}/cases",
    response_model=CaseQueueView,
    response_model_exclude_none=True,
    responses=_error_responses(
        ApiErrorCode.RESOURCE_NOT_FOUND,
        ApiErrorCode.REQUEST_VALIDATION_FAILED,
        ApiErrorCode.INTERNAL_ERROR,
    ),
)
async def list_cases(
    batch_id: str,
    status: Annotated[
        str | None,
        Query(description="只允许一个案例状态筛选"),
    ] = None,
    intervention_level: Annotated[
        str | None,
        Query(description="只允许一个介入等级筛选"),
    ] = None,
    limit: LimitParam = 50,
    offset: OffsetParam = 0,
    services: ApplicationServices | None = Depends(get_services),
) -> CaseQueueView:
    """案例队列；服务端固定排序，不提供 sort_by（M3-04）。"""
    svc = _require_services(services)
    try:
        return svc.list_cases(
            batch_id,
            status=status,
            intervention_level=intervention_level,
            limit=limit,
            offset=offset,
        )
    except ServiceError as error:
        raise _service_response_error(error) from None


@api_router.get(
    "/batches/{batch_id}/cases/{case_id}",
    response_model=CaseDetailView,
    response_model_exclude_none=True,
    responses=_error_responses(
        ApiErrorCode.RESOURCE_NOT_FOUND,
        ApiErrorCode.REQUEST_VALIDATION_FAILED,
        ApiErrorCode.INTERNAL_ERROR,
    ),
)
async def get_case(
    batch_id: str,
    case_id: str,
    services: ApplicationServices | None = Depends(get_services),
) -> CaseDetailView:
    """案例详情（M3-04）。"""
    svc = _require_services(services)
    try:
        return svc.get_case_detail(batch_id, case_id)
    except ServiceError as error:
        raise _service_response_error(error) from None


@api_router.post(
    "/batches/{batch_id}/cases/{case_id}/reruns",
    status_code=202,
    response_model=CaseDetailView,
    response_model_exclude_none=True,
    responses=_error_responses(
        ApiErrorCode.RESOURCE_NOT_FOUND,
        ApiErrorCode.ACTIVE_CASE_RUN_EXISTS,
        ApiErrorCode.CASE_NOT_RERUNNABLE,
        ApiErrorCode.CASE_ALREADY_COMPLETED,
        ApiErrorCode.ANALYSIS_UNAVAILABLE,
        ApiErrorCode.REQUEST_VALIDATION_FAILED,
        ApiErrorCode.INTERNAL_ERROR,
    ),
)
async def rerun_case(
    batch_id: str,
    case_id: str,
    services: ApplicationServices | None = Depends(get_services),
) -> CaseDetailView:
    """人工从头重跑单个案例；无请求体（M3-06 实现）。"""
    raise NotImplementedError("M3-06 实现重跑")


@api_router.post(
    "/batches/{batch_id}/cases/{case_id}/reviews",
    status_code=201,
    response_model=ReviewResultView,
    response_model_exclude_none=True,
    responses={
        200: {"model": ReviewResultView, "description": "相同 submission_id 幂等命中"},
        **_error_responses(
            ApiErrorCode.RESOURCE_NOT_FOUND,
            ApiErrorCode.STALE_CASE_RESULT,
            ApiErrorCode.CASE_ALREADY_COMPLETED,
            ApiErrorCode.REQUEST_VALIDATION_FAILED,
            ApiErrorCode.INTERNAL_ERROR,
        ),
    },
)
async def submit_review(
    batch_id: str,
    case_id: str,
    request: Annotated[ReviewRequest, Field(description="四种人工确认请求之一")],
    services: ApplicationServices | None = Depends(get_services),
) -> ReviewResultView:
    """提交人工确认；相同 submission_id 返回第一次保存结果（M3-07 实现）。"""
    raise NotImplementedError("M3-07 实现人工确认")


@api_router.get(
    "/batches/{batch_id}/cases/{case_id}/evidence/{evidence_id}/content",
    response_class=Response,
    responses={
        200: {
            "description": "受控证据图片流",
            "content": {"image/*": {"schema": {"type": "string", "format": "binary"}}},
        },
        **_error_responses(
            ApiErrorCode.RESOURCE_NOT_FOUND,
            ApiErrorCode.UNSUPPORTED_MEDIA_TYPE,
            ApiErrorCode.REQUEST_VALIDATION_FAILED,
            ApiErrorCode.INTERNAL_ERROR,
        ),
    },
)
async def get_evidence_content(
    batch_id: str,
    case_id: str,
    evidence_id: str,
    services: ApplicationServices | None = Depends(get_services),
) -> Response:
    """按作用域标识读取证据图片；不返回本机路径（M3-04）。"""
    svc = _require_services(services)
    try:
        content = svc.get_evidence_content(batch_id, case_id, evidence_id)
    except ServiceError as error:
        raise _service_response_error(error) from None
    return Response(
        content=content.content,
        media_type=content.media_type,
        headers={
            "Content-Disposition": f'inline; filename="{content.filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


def create_contract_app(
    settings: Settings | None = None,
    services: ApplicationServices | None = None,
    run_service: RunService | None = None,
) -> FastAPI:
    """组合十个接口与错误边界，作为 OpenAPI 快照与合同测试的真源。

    生产装配由应用工厂在 M3-08 注入真实 M1 端口与 M2 引擎；测试注入 Fake。
    """
    app = FastAPI(title="PSIT 高价值客户异常售后决策支持 API 合同")
    app.state.settings = settings if settings is not None else Settings.load()
    app.state.services = services
    app.state.run_service = run_service
    app.include_router(api_router)
    register_health(app)
    install_error_boundary(app)
    return app
