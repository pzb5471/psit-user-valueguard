"""M1-06：EvidenceGateway 安全文件流（技术实施规格 5.6/8/11.2/12.1/12.4）。

在 批次→案例→证据 三级定位之后，只允许读取正式运行数据根内、且与证据行
相对路径一致的受控图片字节：

- 只支持 modality=="image" 且 media_type 为 image/jpeg|image/png|image/gif，
  文本/行为证据与未知媒体类型抛 UnsupportedMediaTypeError（415）；
- 正式目录由批次 package_relative_path（batches/<batch_id>/<data_version>）
  拼接 formal_root 并 resolve，且必须仍位于 formal_root 内；证据候选路径再
  拼证据 relative_path 并 resolve，必须位于正式目录内，否则一律按证据不可用
  处理（404），不泄漏本机绝对路径；
- 文件字节的 sha256 必须与证据行 content_hash 一致，否则视为不可用（404）；
  gif 原样返回、不转换（卡片禁止事项）。

显式假设（超出规格字面处在此声明，供 M3 与人工 PR 复审）：
- 文本/行为证据没有文件流（relative_path 为空串），返回 415 而非 404；
- 缺失/损坏/越界统一使用 message"证据内容不可用"，不区分原因避免信息泄露；
- EvidenceContent.filename 取受控文件名：不得为空、.、.. 或包含分隔符与
  NUL 字符，防止把目录或伪装文件名暴露给下游；
- 正式目录 resolve 后必须仍位于 formal_root 内（防 package_relative_path 被
  篡改为越界目录的纵深防御）。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from sqlalchemy.engine import Engine

from ..db.models import Evidence
from .errors import EvidenceNotFoundError, UnsupportedMediaTypeError
from .repository import EvidenceRepository

SUPPORTED_IMAGE_MEDIA_TYPES = frozenset({"image/jpeg", "image/png", "image/gif"})


@dataclass(frozen=True, slots=True)
class EvidenceContent:
    """受控证据文件流：文件名、媒体类型、原始字节与 sha256 内容哈希。"""

    filename: str
    media_type: str
    content: bytes
    content_hash: str


class EvidenceGateway:
    """SQLite 版 EvidenceGateway：按公开标识安全读取图片证据文件流。"""

    def __init__(self, *, engine: Engine, formal_root: Path) -> None:
        self.formal_root = Path(formal_root).resolve()
        self.repository = EvidenceRepository(engine)

    def get_evidence_content(
        self, batch_id: str, case_id: str, evidence_id: str
    ) -> EvidenceContent:
        """三级定位后校验媒体类型、路径越界与内容哈希，返回受控字节流。"""
        batch = self.repository.batch_by_batch_id(batch_id)
        if batch is None:
            raise EvidenceNotFoundError(object_type="batch", object_id=batch_id)
        case = self.repository.case_of_batch(batch.id, case_id)
        if case is None:
            raise EvidenceNotFoundError(object_type="case", object_id=case_id)
        evidence = self.repository.evidence_of_case(case.id, evidence_id)
        if evidence is None:
            raise EvidenceNotFoundError(object_id=evidence_id)

        if not _is_supported_image(evidence):
            raise UnsupportedMediaTypeError(object_id=evidence_id)

        formal_dir = (
            self.formal_root.joinpath(*PurePosixPath(batch.package_relative_path).parts)
        ).resolve()
        if not formal_dir.is_relative_to(self.formal_root):
            raise EvidenceNotFoundError(object_type="batch", object_id=batch_id)

        relative_path = _validated_relative_path(evidence.relative_path)
        candidate = (formal_dir / relative_path).resolve()
        if not candidate.is_relative_to(formal_dir):
            raise EvidenceNotFoundError(object_id=evidence_id)

        try:
            content = candidate.read_bytes()
        except OSError:
            raise EvidenceNotFoundError(object_id=evidence_id) from None

        content_hash = hashlib.sha256(content).hexdigest()
        if content_hash != evidence.content_hash:
            raise EvidenceNotFoundError(object_id=evidence_id)

        return EvidenceContent(
            filename=_controlled_filename(relative_path),
            media_type=evidence.media_type,
            content=content,
            content_hash=content_hash,
        )


def _is_supported_image(evidence: Evidence) -> bool:
    """只放行 modality=="image" 且媒体类型受支持的证据（规格 5.6/11.2）。"""
    return (
        evidence.modality == "image"
        and evidence.media_type in SUPPORTED_IMAGE_MEDIA_TYPES
    )


def _validated_relative_path(relative_path: str) -> str:
    """返回受控相对路径；文件名非法（空/. /.. /含分隔符与 NUL）按不可用处理。"""
    _controlled_filename(relative_path)
    return relative_path


def _controlled_filename(relative_path: str) -> str:
    """取受控文件名：不得为空、.、.. 或包含 /、\\、NUL（防伪装与逃逸）。"""
    name = PurePosixPath(relative_path).name
    if not name or name in (".", "..") or any(
        ch in name for ch in ("/", "\\", chr(0))
    ):
        raise EvidenceNotFoundError()
    return name


__all__ = ["EvidenceContent", "EvidenceGateway"]
