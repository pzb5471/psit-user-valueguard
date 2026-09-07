"""HTTP API v1 路由签名与 OpenAPI 真源（技术实施规格 12 节；M3-03）。

本模块只冻结十个接口的方法、路径、参数、成功码、允许状态码与
请求/响应模型；处理器体是签名占位，业务实现分别由 M3-04（导入与
读取）、M3-05（批次开始）、M3-06（重跑）、M3-07（人工确认）落地。
health 路由由 M3-02 的 ``register_health`` 提供，本文件不重复注册，
``create_contract_app`` 组合两者供 OpenAPI 快照与合同测试使用。

开始批量分析和重跑没有 JSON 请求体；模型参数、并发、Prompt 和
运行编号不能由页面传入（规格 12.1）。
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, FastAPI, File, Query, Response, UploadFile
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
) -> BatchWorkspaceView:
    """上传一个标准 ZIP 新建批次；重复包 200 幂等命中（M3-04 实现）。"""
    raise NotImplementedError("M3-04 实现导入")


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
) -> BatchListView:
    """按 imported_at 倒序、batch_id 稳定排序列出批次（M3-04 实现）。"""
    raise NotImplementedError("M3-04 实现批次列表")


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
async def get_batch(batch_id: str) -> BatchWorkspaceView:
    """读取单个批次工作台视图（M3-04 实现）。"""
    raise NotImplementedError("M3-04 实现批次详情")


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
async def start_batch_run(batch_id: str) -> BatchWorkspaceView:
    """开始首次批量分析；无请求体，缺密钥时 503（M3-05 实现）。"""
    raise NotImplementedError("M3-05 实现批次开始")


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
) -> CaseQueueView:
    """案例队列；服务端固定排序，不提供 sort_by（M3-04 实现）。"""
    raise NotImplementedError("M3-04 实现案例队列")


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
async def get_case(batch_id: str, case_id: str) -> CaseDetailView:
    """案例详情；can_review=true 时携带 review_token 与 review_options（M3-04 实现）。"""
    raise NotImplementedError("M3-04 实现案例详情")


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
async def rerun_case(batch_id: str, case_id: str) -> CaseDetailView:
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
    batch_id: str, case_id: str, evidence_id: str
) -> Response:
    """按作用域标识读取证据图片；不返回本机路径（M3-04 实现）。"""
    raise NotImplementedError("M3-04 实现证据读取")


def create_contract_app(settings: Settings | None = None) -> FastAPI:
    """组合十个接口与错误边界，作为 OpenAPI 快照与合同测试的真源。

    生产装配由应用工厂在 M3-04 接线；本函数不承载业务实现。
    health 处理器读取 app.state.settings 判定分析可用性。
    """
    app = FastAPI(title="PSIT 高价值客户异常售后决策支持 API 合同")
    app.state.settings = settings if settings is not None else Settings.load()
    app.include_router(api_router)
    register_health(app)
    install_error_boundary(app)
    return app
