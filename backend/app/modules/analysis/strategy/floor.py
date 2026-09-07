"""最低介入规则底线（M2-07，规格第 7.4 节）。

派生程序底线所需的两个事实输入：是否存在未解决的严重问题、是否存在
证据冲突或证据不足。派生规则是 Task 内部实现默认值（规格第 3.2 节），
偏向介入一侧；调整时必须同步更新本模块测试。
"""

from __future__ import annotations

from app.contracts.analysis import (
    AttributionFallbackCause,
    AttributionResult,
    BusinessCause,
    PerceptionResult,
    ResolutionStatus,
)

__all__ = ["derive_intervention_floor"]

_SEVERE_CAUSE_DOMAINS = frozenset(
    {
        BusinessCause.LOGISTICS_FULFILLMENT,
        BusinessCause.PRODUCT_ISSUE,
        BusinessCause.RETURN_REFUND,
    }
)


def derive_intervention_floor(
    perception: PerceptionResult, attribution: AttributionResult
) -> tuple[bool, bool]:
    """返回（是否存在未解决严重问题，是否存在证据冲突或证据不足）。

    - 严重问题：原因落在物流履约、商品问题、退货退款三个严重领域，且感知
      存在未解决或无法确认的事件（规格第 7.4 节的严重问题清单）。
    - 证据冲突或不足：感知存在冲突证据或无法确认事件，或归因已使用
      INSUFFICIENT_EVIDENCE 兜底。
    """

    causes = [attribution.primary_cause]
    if attribution.alternative_cause is not None:
        causes.append(attribution.alternative_cause)
    severe_cause_present = any(cause.category in _SEVERE_CAUSE_DOMAINS for cause in causes)
    unresolved_events = any(
        event.resolution is not ResolutionStatus.RESOLVED for event in perception.events
    )
    severe_unresolved_present = severe_cause_present and unresolved_events

    evidence_conflict_or_insufficient = (
        attribution.primary_cause.category is AttributionFallbackCause.INSUFFICIENT_EVIDENCE
        or any(
            event.conflict_evidence_ids for event in perception.events
        )
        or any(
            event.resolution is ResolutionStatus.UNCONFIRMABLE
            for event in perception.events
        )
    )
    return severe_unresolved_present, evidence_conflict_or_insufficient
