"""M1-09 对话拆分：把客服对话按行拆成确定性消息序列（技术实施规格 5.6）。

锁定规则（已在源数据全量验证）：
- 先规范化图片标签（`[图片1]` → `[图片 1]`），再按换行符拆分；
- 每行 strip 后处理；空行跳过但保留当前角色（使裸标签后的空行不重置角色）；
- 单独成行的 `User:` / `Assistant:` 只切换角色、不产生消息；
- 带内容前缀的行切换角色并产生消息，去掉前缀；
- 无前缀续行归当前角色；当前角色为空时归 CUSTOMER（源数据不会出现）；
- 每个非空内容行独立成为一条 text item，sequence_no 从 1 全局递增。

返回条目结构（直接可用于 TextEvidenceItem 的 dict 化）：
    {"sequence_no": int, "role": "CUSTOMER"|"SERVICE_AGENT", "text": str}
"""

from __future__ import annotations

from .sanitize import IMAGE_TAG_PATTERN

ROLE_CUSTOMER = "CUSTOMER"
ROLE_SERVICE_AGENT = "SERVICE_AGENT"

_CUSTOMER_PREFIX = "User:"
_AGENT_PREFIX = "Assistant:"


def parse_role_prefix(line: str) -> tuple[str | None, str | None]:
    """解析单行：返回 (role, content)；content 为 None 表示仅角色切换。

    - `User:` 单独成行 → ("CUSTOMER", None)
    - `User: 内容` → ("CUSTOMER", "内容")
    - 无前缀 → (None, None)，内容整行作为续行处理
    """
    if line == _CUSTOMER_PREFIX:
        return ROLE_CUSTOMER, None
    if line == _AGENT_PREFIX:
        return ROLE_SERVICE_AGENT, None
    if line.startswith(_CUSTOMER_PREFIX):
        return ROLE_CUSTOMER, line[len(_CUSTOMER_PREFIX) :].strip()
    if line.startswith(_AGENT_PREFIX):
        return ROLE_SERVICE_AGENT, line[len(_AGENT_PREFIX) :].strip()
    return None, None


def split_conversation(text: str) -> list[dict[str, object]]:
    """按锁定规则拆分对话，返回按 role/text 组织的消息条目列表。"""
    normalized = IMAGE_TAG_PATTERN.sub(r"[图片 \1]", text)
    items: list[dict[str, object]] = []
    current_role: str = ROLE_CUSTOMER
    sequence_no = 0
    for raw_line in normalized.split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        role, content = parse_role_prefix(line)
        if role is not None:
            current_role = role
            if content is None:
                continue
            message_text = content
        else:
            if current_role is None:
                current_role = ROLE_CUSTOMER
            message_text = line
        sequence_no += 1
        items.append(
            {
                "sequence_no": sequence_no,
                "role": current_role,
                "text": message_text,
            }
        )
    return items
