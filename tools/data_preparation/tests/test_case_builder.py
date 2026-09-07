"""M1-09 案例构造单元测试（技术实施规格 5.5—5.6）：主订单匹配、行为证据、图片类型与密封参考。"""

import json
from decimal import Decimal

import pytest

from tools.data_preparation.case_builder import (
    RULE_VERSION,
    SEALED_KEYS,
    MainOrder,
    behavior_value_hash,
    build_behavior_items,
    build_image_items,
    build_text_items,
    detect_image,
    match_main_order,
    sealed_fields,
    sha256_bytes,
    sha256_text,
)
from tools.data_preparation.conversation import ROLE_CUSTOMER, ROLE_SERVICE_AGENT
from tools.data_preparation.rfm import CustomerProfile, RfmThresholds

# ---------- 主订单匹配 ----------


def _rows_for_match() -> list[dict[str, str]]:
    return [
        {
            "order_id": "o2",
            "conversation": "  你好  ",
            "payment_value": "10",
            "customer_unique_id": "c1",
        },
        {
            "order_id": "o1",
            "conversation": "你好",
            "payment_value": "20",
            "customer_unique_id": "c1",
        },
        {
            "order_id": "o3",
            "conversation": "别的",
            "payment_value": "30",
            "customer_unique_id": "c2",
        },
    ]


def test_match_main_order_takes_min_order_id_and_strips() -> None:
    order = match_main_order(_rows_for_match(), "你好")
    assert order is not None
    assert order.order_id == "o1"
    assert order.payment_total() == Decimal("20")


def test_match_main_order_aggregates_split_payment_rows() -> None:
    rows = [
        {
            "order_id": "o1",
            "conversation": "你好",
            "payment_value": "10",
            "customer_unique_id": "c1",
        },
        {
            "order_id": "o1",
            "conversation": "你好",
            "payment_value": "5",
            "customer_unique_id": "c1",
        },
    ]
    order = match_main_order(rows, "你好")
    assert order is not None
    assert order.payment_total() == Decimal("15")
    assert len(order.rows) == 2


def test_match_main_order_no_match_returns_none() -> None:
    assert match_main_order(_rows_for_match(), "不在对话里") is None


# ---------- 行为证据 ----------


def _order() -> MainOrder:
    main_row = {
        "order_id": "o1",
        "customer_unique_id": "c1",
        "order_status": "delivered",
        "order_purchase_timestamp": "2017-10-02 10:56:33",
        "order_approved_at": "2017-10-02 11:00:00",
        "order_delivered_carrier_date": "",
        "order_delivered_customer_date": "  ",
        "order_estimated_delivery_date": "2017-10-15 00:00:00",
        "payment_value": "72.2",
    }
    return MainOrder(main_row=main_row, rows=[main_row])


def _profile() -> CustomerProfile:
    return CustomerProfile(
        "c1", recency_days=10, frequency_orders=5, monetary_total=Decimal("300"),
        is_high_value=True,
    )


def _thresholds() -> RfmThresholds:
    return RfmThresholds(Decimal("397"), Decimal("209.604"), Decimal("108"))


def test_behavior_items_order_and_blank_omission() -> None:
    items = build_behavior_items(_order(), _profile(), _thresholds())
    assert [item["fact_type"] for item in items] == [
        "HIGH_VALUE_CUSTOMER",
        "ORDER_STATUS",
        "ORDER_PURCHASED_AT",
        "ORDER_APPROVED_AT",
        "ORDER_ESTIMATED_DELIVERY_AT",
        "ORDER_PAYMENT_TOTAL",
    ]
    hv = items[0]
    assert hv["value"] is True
    assert hv["calculation_rule"] == RULE_VERSION
    assert items[-1]["value"] == "72.2"


def test_behavior_item_hash_matches_formula() -> None:
    items = build_behavior_items(_order(), _profile(), _thresholds())
    status = next(item for item in items if item["fact_type"] == "ORDER_STATUS")
    assert status["content_hash"] == behavior_value_hash("delivered")
    assert status["content_hash"] == sha256_text(
        json.dumps("delivered", ensure_ascii=False)
    )


# ---------- 图片证据 ----------


def test_detect_image_by_magic() -> None:
    assert detect_image(b"\xff\xd8\xff\xe0\x00") == ("image/jpeg", ".jpg")
    assert detect_image(b"\x89PNG\r\n\x1a\n\x00\x00") == ("image/png", ".png")
    assert detect_image(b"GIF89a\x01\x00\x01") == ("image/gif", ".gif")
    assert detect_image(b"GIF87a\x01\x00\x01") == ("image/gif", ".gif")
    assert detect_image(b"not an image at all") is None


def test_build_image_items_infers_extension_and_hash(tmp_path) -> None:
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
    (tmp_path / "pic.dat").write_bytes(png)
    items, assets = build_image_items(
        source_root=tmp_path,
        task_id="t1",
        image_paths=["pic.dat"],
        case_id="demo_case_001",
    )
    assert len(items) == 1
    item = items[0]
    assert item["asset_relative_path"] == "assets/demo_case_001/01.png"
    assert item["media_type"] == "image/png"
    assert item["content_hash"] == sha256_bytes(png)
    assert assets == {"assets/demo_case_001/01.png": png}


def test_build_image_items_unknown_magic_raises(tmp_path) -> None:
    (tmp_path / "bad.dat").write_text("hello", encoding="utf-8")
    with pytest.raises(ValueError, match="无法识别图片类型"):
        build_image_items(
            source_root=tmp_path,
            task_id="t1",
            image_paths=["bad.dat"],
            case_id="c1",
        )


# ---------- 密封参考 ----------


def test_sealed_fields_extracts_only_sealed_keys() -> None:
    task = {
        "task_id": "t1",
        "key_answer": ["答案"],
        "label": 1,
        "trajectory": [],
        "user_profile_st1": {"mood": "平静", "reason": "尺码不合适"},
        "conversation": "不要密封对话",
        "image_paths": [],
    }
    extracted = sealed_fields(task)
    assert set(extracted) == {"key_answer", "label", "trajectory", "user_profile_st1"}
    assert "conversation" not in extracted
    assert "image_paths" not in extracted
    # 嵌套的 mood/reason 等随 user_profile_st1 整体密封，不进入运行包
    assert extracted["user_profile_st1"]["mood"] == "平静"


def test_sealed_keys_include_runtime_leak_keys() -> None:
    from app.modules.data.importing.zip_stage import (
        _ANSWER_LEAK_KEYS,
        _UNSANITIZED_KEYS,
    )

    sealed = set(SEALED_KEYS)
    # mood/reason/solution/image_verification 在源数据中嵌于 user_profile_st1 内
    assert _ANSWER_LEAK_KEYS - {"mood", "reason", "solution", "image_verification"} <= sealed
    assert _UNSANITIZED_KEYS <= sealed
    assert "first_query" in sealed


# ---------- 文本证据 ----------


def test_build_text_items_roles_and_sequence() -> None:
    items = build_text_items("t1", "User: a\nAssistant: b")
    assert [item["role"] for item in items] == [ROLE_CUSTOMER, ROLE_SERVICE_AGENT]
    assert items[0]["evidence_id"] == "ev_text_001"
    assert items[0]["content_hash"] == sha256_text("a")
