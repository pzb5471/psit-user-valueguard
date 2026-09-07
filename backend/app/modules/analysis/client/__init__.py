"""M2 分析模块唯一模型客户端子包（M2-03）：真实 GlmClient、同合同测试客户端、
请求清单与供应商错误分类。三个阶段不直接调用 zai-sdk。"""

from app.modules.analysis.client.client import AnalysisModelClient, GlmClient
from app.modules.analysis.client.errors import (
    GlmClientError,
    classify_provider_error,
)
from app.modules.analysis.client.manifest import (
    REQUEST_MANIFEST_VERSION,
    build_request_manifest,
)
from app.modules.analysis.client.models import (
    GlmCallParams,
    GlmRequest,
    GlmResponse,
    ImageAttachment,
)
from app.modules.analysis.client.testing import ScriptedGlmClient

__all__ = [
    "REQUEST_MANIFEST_VERSION",
    "AnalysisModelClient",
    "GlmCallParams",
    "GlmClient",
    "GlmClientError",
    "GlmRequest",
    "GlmResponse",
    "ImageAttachment",
    "ScriptedGlmClient",
    "build_request_manifest",
    "classify_provider_error",
]
