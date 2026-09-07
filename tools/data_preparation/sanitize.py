"""M1-09 文本脱敏：客服对话的可复算规范化与敏感信息替换（技术实施规格 5.4/5.6）。

替换顺序为锁定顺序（先地址、后长单号、再电话与 URL），空位与空白不影响结果：
1. 规范化图片标签 `[图片1]` → `[图片 1]`；
2. 完整行政区划 + 路/街/大道地址 → `[地址已脱敏]`；
3. 破折号分隔地址（如 `台湾-高雄-盐埕区-三5段民权路155号`）→ `[地址已脱敏]`；
4. 连续 8 位以上数字（物流单号）→ `[单号已脱敏]`；
5. 手机号 → `[已脱敏]`；URL → `[已脱敏]`。

纯行政区划（如 `内蒙古自治区包头市九原区`）不包含路/街，按锁定决策保持不变；
替换只影响来源对话文本，不改动角色前缀与消息结构。
"""

from __future__ import annotations

import re

# 图片标签：`[图片1]` / `[图片 1]` / `[图片  1]` 统一为 `[图片 1]`。
IMAGE_TAG_PATTERN = re.compile(r"\[图片\s*(\d+)\]")

# 完整地址：省/自治区 + 市 + 区/县 + 路/街/大道（含门牌号），命中即整体替换。
ADDRESS_FULL_PATTERN = re.compile(
    r"[\u4e00-\u9fa5]{1,8}(?:省|自治区)[\u4e00-\u9fa5]{2,8}市"
    r"[\u4e00-\u9fa5]{2,15}(?:区|县)[\u4e00-\u9fa5\d\-]*(?:路|街|大道)"
    r"[\u4e00-\u9fa5\d\-]*(?:\d+号|号)?"
)

# 破折号分隔地址：台湾-高雄-前镇区-二2段民生路105号 等。
ADDRESS_DASH_PATTERN = re.compile(
    r"[\u4e00-\u9fa5]{1,8}(?:省|自治区)?[－-][\u4e00-\u9fa5]{2,8}市?"
    r"[－-][\u4e00-\u9fa5]{2,15}(?:区|县)[－-][\u4e00-\u9fa5\d－-]*"
    r"(?:路|街|大道)[\u4e00-\u9fa5\d－-]*(?:\d+号|号)?"
)

# 连续 8 位以上数字：物流单号等长数字串。
TRACKING_NUMBER_PATTERN = re.compile(r"\d{8,}")

# 大陆手机号：1 开头 11 位。
PHONE_PATTERN = re.compile(r"1[3-9]\d{9}")

# URL。
URL_PATTERN = re.compile(r"https?://\S+")

ADDRESS_REDACTED = "[地址已脱敏]"
TRACKING_REDACTED = "[单号已脱敏]"
GENERIC_REDACTED = "[已脱敏]"


def sanitize_conversation(text: str) -> str:
    """按锁定顺序对对话文本执行确定性脱敏，返回无敏感信息的文本。"""
    text = IMAGE_TAG_PATTERN.sub(r"[图片 \1]", text)
    text = ADDRESS_FULL_PATTERN.sub(ADDRESS_REDACTED, text)
    text = ADDRESS_DASH_PATTERN.sub(ADDRESS_REDACTED, text)
    text = TRACKING_NUMBER_PATTERN.sub(TRACKING_REDACTED, text)
    text = PHONE_PATTERN.sub(GENERIC_REDACTED, text)
    text = URL_PATTERN.sub(GENERIC_REDACTED, text)
    return text
