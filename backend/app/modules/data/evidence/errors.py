"""M1-06：EvidenceGateway 错误合同（技术实施规格 12.4 子集）。

证据流接口（M3 提供 GET /api/v1/.../evidence/{evidence_id}/content）的可预期
失败以 EvidenceGatewayError 子类抛出，字段对齐规格 12.4：

- code：稳定错误编号（RESOURCE_NOT_FOUND / UNSUPPORTED_MEDIA_TYPE）；
- stage：内部阶段定位（evidence）；
- message：中文可操作说明，不泄漏本机绝对路径；
- object_type/object_id：公开对象标识（batch/case/evidence 与公开 ID）；
- next_action：中文下一步动作。

证据缺失、文件读取失败、内容哈希不符或被识别为路径越界一律按"不可用"处理
（统一 message，不区分原因、不暴露绝对路径），由 M3 映射为 404。
"""

from __future__ import annotations

#: 证据内容不可用的统一中文说明（不区分缺失/损坏/越界，避免信息泄露）。
_UNAVAILABLE_MESSAGE = "证据内容不可用"


class EvidenceGatewayError(Exception):
    """证据流可预期失败基类（字段对齐规格 12.4）。"""

    def __init__(
        self,
        *,
        code: str,
        message: str,
        object_type: str = "evidence",
        object_id: str = "",
        stage: str = "evidence",
        next_action: str = "检查证据文件后重试",
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.object_type = object_type
        self.object_id = object_id
        self.stage = stage
        self.next_action = next_action


class EvidenceNotFoundError(EvidenceGatewayError):
    """证据不可用：记录不存在、文件缺失、哈希不符或路径越界（M3 映射 404）。"""

    def __init__(self, *, object_type: str = "evidence", object_id: str = "") -> None:
        super().__init__(
            code="RESOURCE_NOT_FOUND",
            message=_UNAVAILABLE_MESSAGE,
            object_type=object_type,
            object_id=object_id,
            stage="evidence",
            next_action="检查证据文件后重试",
        )


class UnsupportedMediaTypeError(EvidenceGatewayError):
    """证据模态/媒体类型不被证据流支持（M3 映射 415；规格 12.4）。"""

    def __init__(self, *, object_type: str = "evidence", object_id: str = "") -> None:
        super().__init__(
            code="UNSUPPORTED_MEDIA_TYPE",
            message="不支持的证据媒体类型",
            object_type=object_type,
            object_id=object_id,
            stage="evidence",
            next_action="更换为支持的图片格式后重试",
        )


__all__ = ["EvidenceGatewayError", "EvidenceNotFoundError", "UnsupportedMediaTypeError"]
