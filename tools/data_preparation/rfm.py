"""M1-09 RFM 复算：全客户交易快照上的确定性 Decimal 计算（技术实施规格 5.3）。

- snapshot_at 取当前数据版本中最大的 order_purchase_timestamp。
- R 为 snapshot_at 减该客户最近一次下单时间的完整天数。
- F 为该客户不同 order_id 的数量，不受付款拆行影响。
- M 为该客户所有 payment_value 的总和；付款拆行先按真实付款记录求和。
- P75(R)、P80(M)、P50(M) 使用线性分位数（h=(n-1)*p，lo/hi 插值）。
- 唯一判定公式：R <= P75(R) AND (M >= P80(M) OR (F >= 2 AND M >= P50(M)))，
  比较使用 <= / >=，等于边界的客户全部纳入。

旧 Notebook 的 F>=10、M>=800、R<=500 只供历史对照，不作为规则。
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

RULE_VERSION = "high_value_rule_v1"

_P = Decimal


def linear_quantile(values: list[Decimal], p: Decimal) -> Decimal:
    """线性分位数：h=(n-1)*p；lo=floor(h)；hi=lo+1（lo<n-1 时），否则 hi=lo。"""
    ordered = sorted(values)
    n = len(ordered)
    if n == 0:
        raise ValueError("空序列无法计算分位数")
    h = Decimal(n - 1) * p
    lo = int(h)
    hi = lo + 1 if lo < n - 1 else lo
    if lo == hi:
        return ordered[lo]
    frac = h - lo
    return ordered[lo] * (Decimal(1) - frac) + ordered[hi] * frac


@dataclass(frozen=True)
class RfmThresholds:
    """三个实际分位边界（规格 5.3 复算结果）。"""

    r_p75: Decimal
    m_p80: Decimal
    m_p50: Decimal

    @property
    def r_p75_text(self) -> str:
        """展示文本：R 边界保留两位小数（当前数据为 '397.00'）。"""
        return format(self.r_p75.quantize(Decimal("0.01")), "f")

    @property
    def m_p80_text(self) -> str:
        """展示文本：M 边界保留三位小数（当前数据为 '209.604'）。"""
        return format(self.m_p80.quantize(Decimal("0.001")), "f")

    @property
    def m_p50_text(self) -> str:
        """展示文本：M 边界保留两位小数（当前数据为 '108.00'）。"""
        return format(self.m_p50.quantize(Decimal("0.01")), "f")


@dataclass(frozen=True)
class CustomerProfile:
    """单一客户的 R/F/M 与判定结果（规格 5.3）。"""

    customer_unique_id: str
    recency_days: int
    frequency_orders: int
    monetary_total: Decimal
    is_high_value: bool

    def decision_reason(self, thresholds: RfmThresholds) -> str:
        """把判定结果写成确定性中文理由（供可复算内部产物与 customer_value）。"""
        r = self.recency_days
        f = self.frequency_orders
        m = self.monetary_total
        r75 = thresholds.r_p75
        m80 = thresholds.m_p80
        m50 = thresholds.m_p50
        m_text = format(m, "f")
        if self.is_high_value:
            if m >= m80:
                return f"R={r}<={r75} 且 M={m_text}>={m80}，满足高价值判定"
            return f"R={r}<={r75} 且 F={f}>=2、M={m_text}>={m50}，满足高价值判定"
        if r > r75:
            return f"R={r}>{r75}，不满足高价值判定"
        if f < 2:
            return f"R={r}<={r75} 但 M={m_text}<{m80} 且 F={f}<2，不满足高价值判定"
        return f"R={r}<={r75} 但 M={m_text}<{m50}，不满足高价值判定"


@dataclass(frozen=True)
class RfmResult:
    """RFM 复算产物：快照、阈值、逐客户画像与总数。"""

    snapshot_at: datetime
    thresholds: RfmThresholds
    profiles: dict[str, CustomerProfile]
    customer_count: int
    high_value_count: int

    def profile_of(self, customer_unique_id: str) -> CustomerProfile:
        try:
            return self.profiles[customer_unique_id]
        except KeyError as exc:
            raise KeyError(f"客户不在 RFM 快照中：{customer_unique_id}") from exc


def _profile_decision(
    customer_unique_id: str,
    recency_days: int,
    frequency_orders: int,
    monetary_total: Decimal,
    thresholds: RfmThresholds,
) -> CustomerProfile:
    is_high_value = recency_days <= thresholds.r_p75 and (
        monetary_total >= thresholds.m_p80
        or (frequency_orders >= 2 and monetary_total >= thresholds.m_p50)
    )
    return CustomerProfile(
        customer_unique_id=customer_unique_id,
        recency_days=int(recency_days),
        frequency_orders=int(frequency_orders),
        monetary_total=monetary_total,
        is_high_value=is_high_value,
    )


def compute_rfm(rows: Iterable[dict[str, str]]) -> RfmResult:
    """在全部客户级交易快照上复算 RFM（规格 5.3，先于固定案例筛选）。"""
    money = defaultdict(Decimal)
    orders: dict[str, set[str]] = defaultdict(set)
    last: dict[str, datetime] = {}
    snapshot: datetime | None = None

    for row in rows:
        customer_id = row["customer_unique_id"]
        purchased_at = datetime.fromisoformat(row["order_purchase_timestamp"].strip())
        if snapshot is None or purchased_at > snapshot:
            snapshot = purchased_at
        money[customer_id] += Decimal(row["payment_value"])
        orders[customer_id].add(row["order_id"])
        previous = last.get(customer_id)
        if previous is None or purchased_at > previous:
            last[customer_id] = purchased_at

    if snapshot is None:
        raise ValueError("清洗后主表没有任何下单时间，无法计算 RFM")

    thresholds = RfmThresholds(
        r_p75=linear_quantile(
            [
                Decimal((snapshot - last[customer_id]).days)
                for customer_id in last
            ],
            Decimal("0.75"),
        ),
        m_p80=linear_quantile(
            [money[customer_id] for customer_id in money], Decimal("0.8")
        ),
        m_p50=linear_quantile(
            [money[customer_id] for customer_id in money], Decimal("0.5")
        ),
    )

    profiles: dict[str, CustomerProfile] = {}
    for customer_id in money:
        recency = Decimal((snapshot - last[customer_id]).days)
        profiles[customer_id] = _profile_decision(
            customer_id,
            recency,
            len(orders[customer_id]),
            money[customer_id],
            thresholds,
        )

    return RfmResult(
        snapshot_at=snapshot,
        thresholds=thresholds,
        profiles=profiles,
        customer_count=len(profiles),
        high_value_count=sum(1 for p in profiles.values() if p.is_high_value),
    )
