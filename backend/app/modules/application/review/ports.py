"""M3-07 人工确认：调用 M1 ReviewStore 的公开端口协议（规格第 8 节）。

只声明 M1 ReviewStore 的 submit_review 能力；幂等、Token 并发保护、字段规则
与状态机由 M1 ReviewStore 在单事务内完成（M1-08 契约）。M3 负责编排与映射。
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from app.modules.data.queries.views import ReviewResultView as DataReviewResultView
from app.modules.data.review_store.types import ReviewSubmitInput


class ReviewStorePort(Protocol):
    """M1 ReviewStore 的人工确认写端口。"""

    def submit_review(
        self,
        *,
        submission_id: str,
        case_run_id: int,
        review_token: str,
        payload: ReviewSubmitInput,
        case_status: object = ...,
        occurred_at: datetime | None = None,
    ) -> DataReviewResultView: ...
