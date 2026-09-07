"""M1-06：EvidenceGateway 安全文件流（技术实施规格 5.6/8/11.2/12.1/12.4）。

对外只暴露证据内容 DTO 与安全读取网关；错误合同见 errors.py，只读仓储见
repository.py。HTTP 证据接口由 M3 提供，本网关只产出受控字节流。
"""

from .errors import (
    EvidenceGatewayError,
    EvidenceNotFoundError,
    UnsupportedMediaTypeError,
)
from .gateway import EvidenceContent, EvidenceGateway

__all__ = [
    "EvidenceContent",
    "EvidenceGateway",
    "EvidenceGatewayError",
    "EvidenceNotFoundError",
    "UnsupportedMediaTypeError",
]
