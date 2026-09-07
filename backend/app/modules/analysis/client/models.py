"""GlmClient 的请求、响应与起跑参数模型（M2-03，规格第 3.2、9.3 节）。

请求只携带当前阶段的获准输入；请求清单与事件合同不携带密钥与完整提示词原文。
起跑参数为规格第 3.2 节的 Task 内部实现默认值，PoC 后由配置冻结。
"""

from __future__ import annotations

from dataclasses import dataclass

from app.contracts.analysis import AnalysisStage

_ALLOWED_IMAGE_MEDIA_TYPES = frozenset({"image/png", "image/jpeg"})


@dataclass(frozen=True)
class ImageAttachment:
    """随请求发送的图片：仅支持 MVP 固定的 PNG 与 JPEG。"""

    media_type: str
    data_base64: str

    def __post_init__(self) -> None:
        if self.media_type not in _ALLOWED_IMAGE_MEDIA_TYPES:
            raise ValueError(f"不支持的图片格式：{self.media_type}")
        if not self.data_base64:
            raise ValueError("图片数据为空")


@dataclass(frozen=True)
class GlmRequest:
    """单次模型调用请求：系统提示词 + 用户输入内容 + 可选图片。"""

    stage: AnalysisStage
    prompt_version: str
    system_prompt: str
    user_content: str
    images: tuple[ImageAttachment, ...] = ()

    def __post_init__(self) -> None:
        if not self.prompt_version.strip():
            raise ValueError("缺少 Prompt 版本")
        if not self.system_prompt.strip():
            raise ValueError("缺少系统提示词")
        if not self.user_content.strip():
            raise ValueError("缺少用户输入内容")


@dataclass(frozen=True)
class GlmResponse:
    """单次模型调用结果：JSON 内容文本与供应商实际返回的可用 Token 计数。"""

    content: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


@dataclass(frozen=True)
class GlmCallParams:
    """起跑参数（规格第 3.2 节默认值）：重试与请求上限归 M2-08 引擎所有。"""

    model_name: str = "glm-5.3-flash"
    max_tokens: int = 4096
    do_sample: bool = False
    thinking_enabled: bool = True
    reasoning_effort: str = "high"
    json_object_mode: bool = True
