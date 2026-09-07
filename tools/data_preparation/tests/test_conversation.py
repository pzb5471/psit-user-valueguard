"""M1-09 对话拆分单元测试（技术实施规格 5.6）：角色切换、裸标签、空行保角色与序号递增。"""

from tools.data_preparation.conversation import (
    ROLE_CUSTOMER,
    ROLE_SERVICE_AGENT,
    split_conversation,
)


def _roles(items: list[dict]) -> list[object]:
    return [item["role"] for item in items]


def _texts(items: list[dict]) -> list[object]:
    return [item["text"] for item in items]


def test_prefixed_lines_become_messages() -> None:
    items = split_conversation("User: 你好\nAssistant: 请问订单号")
    assert _roles(items) == [ROLE_CUSTOMER, ROLE_SERVICE_AGENT]
    assert _texts(items) == ["你好", "请问订单号"]


def test_bare_label_only_switches_role() -> None:
    items = split_conversation("User:\n第一句\nAssistant:\n第二句")
    assert _roles(items) == [ROLE_CUSTOMER, ROLE_SERVICE_AGENT]
    assert _texts(items) == ["第一句", "第二句"]


def test_empty_lines_preserve_current_role() -> None:
    items = split_conversation("User:\n\n图片\n\nAssistant: 回复")
    assert _roles(items) == [ROLE_CUSTOMER, ROLE_SERVICE_AGENT]
    assert _texts(items) == ["图片", "回复"]


def test_no_prefix_continuation_uses_current_role() -> None:
    items = split_conversation("User: 第一行\n续行\nAssistant: 回复")
    assert _roles(items) == [ROLE_CUSTOMER, ROLE_CUSTOMER, ROLE_SERVICE_AGENT]
    assert _texts(items) == ["第一行", "续行", "回复"]


def test_no_prefix_defaults_to_customer() -> None:
    items = split_conversation("首行无前缀")
    assert items[0]["role"] == ROLE_CUSTOMER


def test_sequence_increments_globally() -> None:
    items = split_conversation("User: a\nAssistant: b\nc")
    assert [item["sequence_no"] for item in items] == [1, 2, 3]


def test_case_000011_bare_label_blank_then_lines() -> None:
    items = split_conversation("User:\n\n[图片1]\n照片传了")
    assert _roles(items) == [ROLE_CUSTOMER, ROLE_CUSTOMER]
    assert _texts(items) == ["[图片 1]", "照片传了"]


def test_case_000007_image_tags_normalized_and_kept_on_one_line() -> None:
    items = split_conversation("User: [图片1][图片2][图片3]")
    assert _texts(items) == ["[图片 1][图片 2][图片 3]"]


def test_each_nonempty_line_is_own_item() -> None:
    items = split_conversation("User: 第一行\n\nAssistant: 第二行\n第三行")
    assert _texts(items) == ["第一行", "第二行", "第三行"]
    assert _roles(items) == [ROLE_CUSTOMER, ROLE_SERVICE_AGENT, ROLE_SERVICE_AGENT]
    assert [item["sequence_no"] for item in items] == [1, 2, 3]
