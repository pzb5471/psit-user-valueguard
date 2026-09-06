"""M1-08：ReviewStore 输入 DTO（技术实施规格 8/10.2/12.3）。

submit_review 的载荷：outcome 为四种人工确认结果之一，final_* 与
review_reason 的必填/禁止由 outcome 按 12.3 表格决定（网关统一校验）。
execution_note 在请求中按需出现，但 reviews 表无对应列（规格 11.1 九表
Schema），不落库，见 gateway 显式假设。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ReviewSubmitInput:
    """一条人工确认命令的载荷（规格 12.3）。"""

    outcome: str
    final_intervention_level: str | None = None
    final_cause: dict[str, Any] | None = None
    final_actions: list[dict[str, Any]] | None = None
    review_reason: str | None = None
    execution_note: str | None = None


__all__ = ["ReviewSubmitInput"]
