"""M3 服务层可预期业务异常（M3-04）。

M1 数据端口的拒绝结果与异常在此被映射为稳定业务信号，路由层再据此构造
BusinessError 响应。这里不透传 M1 异常类、ORM 或供应商细节。
"""

from __future__ import annotations

from dataclasses import dataclass

from app.modules.application.api.contracts.errors import (
    ApiErrorCode,
    ProcessingErrorStage,
)


@dataclass(frozen=True, slots=True)
class ServiceError(Exception):
    """稳定的业务错误信号，字段对齐规格 12.4 BusinessError。"""

    code: ApiErrorCode
    message: str
    object_type: str = "request"
    object_id: str = ""
    stage: ProcessingErrorStage = ProcessingErrorStage.INPUT_PREPARATION
    next_action: str = "请检查后重试"
