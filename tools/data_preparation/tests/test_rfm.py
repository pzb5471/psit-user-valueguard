"""M1-09 RFM 复算单元测试（技术实施规格 5.3）：线性分位数、判定理由与全量金值。"""

from datetime import datetime
from decimal import Decimal

import pytest

from tools.data_preparation.rfm import (
    RULE_VERSION,
    CustomerProfile,
    RfmThresholds,
    compute_rfm,
    linear_quantile,
)
from tools.data_preparation.sources import load_csv_rows


@pytest.fixture(scope="module")
def rfm(source_root):
    """模块级一次性复算（约 2–4 秒），供金值断言复用。"""
    rows = load_csv_rows(
        source_root / "dataprocessing" / "output" / "data_with_context.csv"
    )
    return compute_rfm(rows)


# ---------- 线性分位数 ----------


def test_linear_quantile_lower_upper_extremes() -> None:
    values = [Decimal("1"), Decimal("2"), Decimal("3"), Decimal("4")]
    assert linear_quantile(values, Decimal("0")) == Decimal("1")
    assert linear_quantile(values, Decimal("1")) == Decimal("4")


def test_linear_quantile_interpolates() -> None:
    values = [Decimal("1"), Decimal("2"), Decimal("3"), Decimal("4")]
    assert linear_quantile(values, Decimal("0.5")) == Decimal("2.5")


def test_linear_quantile_two_values() -> None:
    values = [Decimal("7"), Decimal("9")]
    assert linear_quantile(values, Decimal("0.75")) == Decimal("8.5")


def test_linear_quantile_empty_raises() -> None:
    with pytest.raises(ValueError):
        linear_quantile([], Decimal("0.5"))


# ---------- 判定公式与理由 ----------


def _thresholds() -> RfmThresholds:
    return RfmThresholds(
        r_p75=Decimal("100"), m_p80=Decimal("200"), m_p50=Decimal("150")
    )


def test_decision_reason_high_value_via_m80() -> None:
    profile = CustomerProfile(
        "c1", 10, 1, Decimal("300"), is_high_value=True
    )
    assert profile.decision_reason(_thresholds()) == (
        "R=10<=100 且 M=300>=200，满足高价值判定"
    )


def test_decision_reason_high_value_via_f2_m50() -> None:
    profile = CustomerProfile(
        "c2", 10, 2, Decimal("160"), is_high_value=True
    )
    assert profile.decision_reason(_thresholds()) == (
        "R=10<=100 且 F=2>=2、M=160>=150，满足高价值判定"
    )


def test_decision_reason_rejected_by_recency() -> None:
    profile = CustomerProfile(
        "c3", 200, 9, Decimal("999"), is_high_value=False
    )
    assert profile.decision_reason(_thresholds()) == "R=200>100，不满足高价值判定"


def test_decision_reason_rejected_by_frequency() -> None:
    profile = CustomerProfile(
        "c4", 10, 1, Decimal("100"), is_high_value=False
    )
    assert profile.decision_reason(_thresholds()) == (
        "R=10<=100 但 M=100<200 且 F=1<2，不满足高价值判定"
    )


def test_decision_reason_rejected_by_monetary() -> None:
    profile = CustomerProfile(
        "c5", 10, 3, Decimal("140"), is_high_value=False
    )
    assert profile.decision_reason(_thresholds()) == (
        "R=10<=100 但 M=140<150，不满足高价值判定"
    )


def test_rule_version_consistent() -> None:
    from tools.data_preparation.case_builder import RULE_VERSION as CASE_RULE

    assert RULE_VERSION == "high_value_rule_v1"
    assert CASE_RULE == RULE_VERSION


# ---------- 合成小数据 ----------


def test_compute_rfm_synthetic() -> None:
    rows = [
        {
            "customer_unique_id": "a",
            "order_id": "o1",
            "order_purchase_timestamp": "2017-01-01 10:00:00",
            "payment_value": "10",
        },
        {
            "customer_unique_id": "a",
            "order_id": "o1",
            "order_purchase_timestamp": "2017-01-01 10:00:00",
            "payment_value": "5",
        },
        {
            "customer_unique_id": "a",
            "order_id": "o2",
            "order_purchase_timestamp": "2017-01-02 10:00:00",
            "payment_value": "100",
        },
        {
            "customer_unique_id": "b",
            "order_id": "o3",
            "order_purchase_timestamp": "2017-01-03 10:00:00",
            "payment_value": "1",
        },
    ]
    result = compute_rfm(rows)
    assert result.snapshot_at == datetime(2017, 1, 3, 10, 0, 0)
    assert result.customer_count == 2
    profile_a = result.profile_of("a")
    assert profile_a.frequency_orders == 2
    assert profile_a.monetary_total == Decimal("115")
    assert profile_a.recency_days == 1
    assert result.profile_of("b").recency_days == 0
    # 唯一判定公式：a 的 R=1 > P75(R)=0.75，故不是高价值
    assert not profile_a.is_high_value


# ---------- 全量金值（依赖逻辑源目录） ----------


def test_gold_customer_and_high_value_counts(rfm) -> None:
    assert rfm.customer_count == 96095
    assert rfm.high_value_count == 15208


def test_gold_threshold_texts(rfm) -> None:
    assert rfm.thresholds.r_p75_text == "397.00"
    assert rfm.thresholds.m_p80_text == "209.604"
    assert rfm.thresholds.m_p50_text == "108.00"
