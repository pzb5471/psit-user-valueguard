"""M1-09 文本脱敏单元测试（技术实施规格 5.6）：图片标签规范化、地址/单号/电话/URL 替换与幂等性。"""

from tools.data_preparation.sanitize import (
    ADDRESS_REDACTED,
    GENERIC_REDACTED,
    PHONE_PATTERN,
    TRACKING_REDACTED,
    sanitize_conversation,
)


def test_image_tag_normalized_without_space() -> None:
    assert sanitize_conversation("[图片1]") == "[图片 1]"


def test_image_tag_with_space_kept_stable() -> None:
    assert sanitize_conversation("[图片 1]") == "[图片 1]"
    assert sanitize_conversation("[图片   2]") == "[图片 2]"
    assert sanitize_conversation("[图片10]") == "[图片 10]"


def test_full_address_redacted() -> None:
    assert sanitize_conversation("广东省深圳市南山区科技园路1号") == ADDRESS_REDACTED


def test_full_address_with_autonomous_region_redacted() -> None:
    assert sanitize_conversation("内蒙古自治区包头市九原区建设路88号") == ADDRESS_REDACTED


def test_taiwan_address_without_dash_redacted() -> None:
    assert sanitize_conversation("台湾省高雄市前镇区二2段民生路105号") == ADDRESS_REDACTED


def test_dash_address_redacted() -> None:
    assert sanitize_conversation("台湾-高雄-盐埕区-三5段民权路155号") == ADDRESS_REDACTED


def test_pure_region_without_street_kept() -> None:
    text = "内蒙古自治区包头市九原区"
    assert sanitize_conversation(text) == text


def test_tracking_number_redacted() -> None:
    assert sanitize_conversation("顺丰单号 3109884139956") == "顺丰单号 " + TRACKING_REDACTED
    assert sanitize_conversation("1234567") == "1234567"


def test_phone_never_survives() -> None:
    sanitized = sanitize_conversation("联系电话 13812345678")
    assert "13812345678" not in sanitized


def test_phone_pattern_unit() -> None:
    assert PHONE_PATTERN.search("13812345678") is not None
    assert PHONE_PATTERN.search("23812345678") is None


def test_url_redacted() -> None:
    assert sanitize_conversation("https://example.com/a?b=c") == GENERIC_REDACTED


def test_sanitize_is_idempotent() -> None:
    samples = (
        "[图片1] 广东省深圳市南山区科技园路1号 单号3109884139956",
        "台湾-高雄-盐埕区-三5段民权路155号 https://example.com/x",
        "内蒙古自治区包头市九原区 13812345678",
    )
    for text in samples:
        once = sanitize_conversation(text)
        assert sanitize_conversation(once) == once
