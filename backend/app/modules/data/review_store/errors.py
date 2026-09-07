"""M1-08：ReviewStore 错误合同（技术实施规格 12.3/12.4）。

ReviewStore 命令的可预期失败以 ReviewStoreError 子类抛出，字段对齐规格
12.4：code / message / object_type / object_id / stage / next_action。
HTTP 状态由 M3 按 code 映射：RESOURCE_NOT_FOUND→404、STALE_CASE_RESULT 与
CASE_ALREADY_COMPLETED→409、REQUEST_VALIDATION_FAILED→422（规格 12.4）。
"""

from __future__ import annotations


class ReviewStoreError(Exception):
    """ReviewStore 可预期失败基类（字段对齐规格 12.4）。"""

    def __init__(
        self,
        *,
        code: str,
        message: str,
        object_type: str = "review",
        object_id: str = "",
        stage: str = "review_store",
        next_action: str = "重新获取案例详情后重试",
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.object_type = object_type
        self.object_id = object_id
        self.stage = stage
        self.next_action = next_action


class ReviewStoreResourceNotFoundError(ReviewStoreError):
    """批次/案例/运行不存在：命令按公开标识定位失败（M3 映射 404）。"""

    def __init__(self, *, object_type: str = "case_run", object_id: str = "") -> None:
        super().__init__(
            code="RESOURCE_NOT_FOUND",
            message="案例运行、案例或批次不存在",
            object_type=object_type,
            object_id=object_id,
            stage="review_store",
            next_action="检查 batch_id/case_id/case_run_id 后重试",
        )


class StaleCaseResultError(ReviewStoreError):
    """review_token 不再对应当前结果，或目标运行已不是当前结果（409）。"""

    def __init__(self, *, object_id: str = "") -> None:
        super().__init__(
            code="STALE_CASE_RESULT",
            message="人工确认已过期：结果已被重跑或新结果替换",
            object_type="case_run",
            object_id=object_id,
            stage="review_store",
            next_action="重新获取案例详情取得新 review_token 后重试",
        )


class CaseAlreadyCompletedError(ReviewStoreError):
    """已完成案例收到新的审核请求（规格 12.3：409 CASE_ALREADY_COMPLETED）。"""

    def __init__(self, *, object_id: str = "") -> None:
        super().__init__(
            code="CASE_ALREADY_COMPLETED",
            message="案例已完成，不能再次提交人工结果",
            object_type="case",
            object_id=object_id,
            stage="review_store",
            next_action="已完成案例只读，无需再次提交",
        )


class ReviewFieldValidationError(ReviewStoreError):
    """人工确认字段不符合规格 12.3 表格（M3 映射 422 REQUEST_VALIDATION_FAILED）。"""

    def __init__(
        self, *, object_id: str = "", message: str = "人工确认字段不符合规则"
    ) -> None:
        super().__init__(
            code="REQUEST_VALIDATION_FAILED",
            message=message,
            object_type="review",
            object_id=object_id,
            stage="review_store",
            next_action="按规格 12.3 表格修正必填/禁止字段后重试",
        )


__all__ = [
    "CaseAlreadyCompletedError",
    "ReviewFieldValidationError",
    "ReviewStoreError",
    "ReviewStoreResourceNotFoundError",
    "StaleCaseResultError",
]
