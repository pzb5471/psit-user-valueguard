"""ZIP 暂存与校验的拒绝报告合同（技术实施规格 12.4；ADR-0026/0067）。

可预期拒绝（坏 ZIP、合同不合格、答案泄漏、媒体不支持、超大小）不抛 Python 异常，
由 ZipImportStage.stage() 聚合为逐项 RejectionInfo 报告返回；意外异常（程序缺陷、
磁盘失败等）保留技术因果链直接抛出，由最近模块边界（M1-04 BatchImportGateway / M3）
映射为 INTERNAL_ERROR。

报告只包含稳定错误编号、中文可操作说明、包内相对路径或公开标识，不含本机绝对路径
与客户正文（M1-03 人工验收：每类拒绝都有稳定编号和可操作说明）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from uuid import uuid4


class ImportRejectionCode(StrEnum):
    """M1-03 阶段可产生的错误编号（规格 12.4 固定编号的子集）。"""

    INVALID_ZIP = "INVALID_ZIP"
    INPUT_CONTRACT_INVALID = "INPUT_CONTRACT_INVALID"
    ANSWER_LEAKAGE_DETECTED = "ANSWER_LEAKAGE_DETECTED"
    UNSUPPORTED_MEDIA_TYPE = "UNSUPPORTED_MEDIA_TYPE"
    UPLOAD_TOO_LARGE = "UPLOAD_TOO_LARGE"


class ImportStage(StrEnum):
    """业务阶段（规格 12.4 stage）：定位拒绝发生在哪一步。"""

    ZIP_STRUCTURE = "zip_structure"
    MANIFEST = "manifest"
    CHECKSUMS = "checksums"
    CASE_CONTRACT = "case_contract"
    MEDIA = "media"
    ANSWER_LEAKAGE = "answer_leakage"
    RELATIONSHIP = "relationship"


@dataclass(frozen=True, slots=True)
class RejectionInfo:
    """单条拒绝：稳定编号 + 中文可操作说明 + 包内对象标识，供 M3 直接业务化展示。"""

    code: ImportRejectionCode
    message: str
    object_type: str
    object_id: str
    stage: ImportStage
    next_action: str
    trace_id: str = field(default_factory=lambda: uuid4().hex)
