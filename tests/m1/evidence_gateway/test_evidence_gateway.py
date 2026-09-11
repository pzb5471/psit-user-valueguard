"""M1-06：EvidenceGateway 安全文件流测试（技术实施规格 5.6/8/11.2/12.1/12.4）。

覆盖证据内容读取的自动验收：
- 合法 JPEG/PNG/GIF 可读：filename/media_type/content/content_hash 与原包一致；
- 批次→案例→证据 三级定位：不存在抛 EvidenceNotFoundError（404）；
- 文本/行为证据不支持文件流：抛 UnsupportedMediaTypeError（415）；
- 路径篡改（../ 越界、反斜杠、绝对路径、空串）按不可用处理（404），错误
  消息不泄漏本机绝对路径；
- 文件被删除、文件字节被替换或数据库哈希被改写按不可用处理（404）；
- 多批次互不串读：批内跨案例取不到、跨批次也取不到。

测试调用 BatchImportGateway.import_zip 落盘正式文件（含 PNG/GIF），再经
EvidenceGateway 读取；篡改用 SQLAlchemy update 直接改写 evidence 行模拟。
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from zip_fixtures import (
    GIF_BYTES,
    JPEG_BYTES,
    PNG_BYTES,
    make_case,
    make_entries,
    make_zip,
)

from app.modules.data.db.models import Batch, Case, Evidence
from app.modules.data.evidence.errors import (
    EvidenceNotFoundError,
    UnsupportedMediaTypeError,
)

# ---------- 测试构造助手 ----------

def _wrapped_case(*, batch_id: str) -> Callable[[str], dict[str, Any]]:
    """改写案例 JSON 的 batch_id，配合 manifest_overrides 导入多批次。"""

    def builder(case_id: str) -> dict[str, Any]:
        payload = make_case(case_id)
        payload["batch_id"] = batch_id
        return payload

    return builder


def _image_case_builder(
    *, batch_id: str, suffix: str, media_type: str, image_bytes: bytes
) -> Callable[[str], dict[str, Any]]:
    """构造指定图片格式的案例构造器（资产路径/媒体类型/哈希与字节一致）。"""

    def builder(case_id: str) -> dict[str, Any]:
        payload = make_case(
            case_id,
            image_suffix=suffix,
            media_type=media_type,
            image_bytes=image_bytes,
        )
        payload["batch_id"] = batch_id
        return payload

    return builder


def _import_batch(
    gateway,
    *,
    batch_id: str,
    case_ids: tuple[str, ...] = ("mvp_case_001", "mvp_case_002"),
    case_builder: Callable[[str], dict[str, Any]] | None = None,
    image_bytes: bytes = JPEG_BYTES,
    image_suffix: str = ".jpg",
    source_filename: str = "upload.zip",
) -> str:
    """导入一个完整标准 ZIP 并返回 batch_id；资产字节与案例声明保持一致。"""
    builder = case_builder or _wrapped_case(batch_id=batch_id)
    entries = make_entries(
        case_ids=case_ids,
        case_builder=builder,
        manifest_overrides={"batch_id": batch_id},
        image_bytes=image_bytes,
        image_suffix=image_suffix,
    )
    result = gateway.import_zip(
        make_zip(entries), source_filename=source_filename, trace_id=f"trace-{batch_id}"
    )
    assert result.ok, result
    assert result.batch_id == batch_id
    return batch_id


def _evidence_file(
    engine: Engine, formal_root: Path, *, batch_id: str, case_id: str, evidence_id: str
) -> tuple[Path, Evidence]:
    """定位证据行对应的正式文件路径与 ORM 行。"""
    with Session(engine) as session:
        batch = session.scalar(select(Batch).where(Batch.batch_id == batch_id))
        assert batch is not None, batch_id
        case = session.scalar(
            select(Case).where(Case.batch_id == batch.id, Case.case_id == case_id)
        )
        assert case is not None, f"{batch_id}/{case_id}"
        row = session.scalar(
            select(Evidence).where(
                Evidence.case_id == case.id, Evidence.evidence_id == evidence_id
            )
        )
        assert row is not None, evidence_id
        file_path = formal_root.joinpath(batch.package_relative_path, row.relative_path)
    return file_path, row


def _tamper_evidence(
    engine: Engine, *, batch_id: str, case_id: str, evidence_id: str, **values: Any
) -> None:
    """用 SQLAlchemy update 直接改写 evidence 行（模拟数据库侧篡改）。"""
    with Session(engine) as session:
        batch = session.scalar(select(Batch).where(Batch.batch_id == batch_id))
        assert batch is not None, batch_id
        case = session.scalar(
            select(Case).where(Case.batch_id == batch.id, Case.case_id == case_id)
        )
        assert case is not None, f"{batch_id}/{case_id}"
        session.execute(
            update(Evidence)
            .where(Evidence.case_id == case.id, Evidence.evidence_id == evidence_id)
            .values(**values)
        )
        session.commit()


# ---------- 合法图片证据 ----------

@pytest.mark.parametrize(
    ("batch_id", "suffix", "media_type", "image_bytes"),
    [
        ("jpeg", ".jpg", "image/jpeg", JPEG_BYTES),
        ("png", ".png", "image/png", PNG_BYTES),
        ("gif", ".gif", "image/gif", GIF_BYTES),
    ],
)
def test_supported_image_content_roundtrip(
    gateway, evidence_gateway, batch_id: str, suffix: str, media_type: str, image_bytes: bytes
) -> None:
    builder = _image_case_builder(
        batch_id=batch_id,
        suffix=suffix,
        media_type=media_type,
        image_bytes=image_bytes,
    )
    _import_batch(
        gateway,
        batch_id=batch_id,
        case_ids=("mvp_case_001",),
        case_builder=builder,
        image_bytes=image_bytes,
        image_suffix=suffix,
    )
    content = evidence_gateway.get_evidence_content(
        batch_id, "mvp_case_001", "ev_image_mvp_case_001"
    )
    assert content.filename == f"scratch_01{suffix}"
    assert content.media_type == media_type
    assert content.content == image_bytes
    assert content.content_hash == hashlib.sha256(image_bytes).hexdigest()


def test_second_case_image_readable(gateway, evidence_gateway) -> None:
    batch_id = _import_batch(gateway, batch_id="second")
    content = evidence_gateway.get_evidence_content(
        batch_id, "mvp_case_002", "ev_image_mvp_case_002"
    )
    assert content.filename == "scratch_01.jpg"
    assert content.content == JPEG_BYTES


# ---------- 三级定位与媒体类型 ----------

def test_missing_batch_case_evidence_not_found(gateway, evidence_gateway) -> None:
    batch_id = _import_batch(gateway, batch_id="missing")
    cases = [
        ("no-such-batch", "mvp_case_001", "ev_image_mvp_case_001"),
        (batch_id, "no-such-case", "ev_image_mvp_case_001"),
        (batch_id, "mvp_case_001", "no-such-evidence"),
    ]
    for batch, case_id, evidence_id in cases:
        with pytest.raises(EvidenceNotFoundError) as exc:
            evidence_gateway.get_evidence_content(batch, case_id, evidence_id)
        assert exc.value.code == "RESOURCE_NOT_FOUND"
        assert exc.value.message == "证据内容不可用"


@pytest.mark.parametrize(
    ("batch_id", "evidence_id"),
    [
        ("text-ev", "ev_text_mvp_case_001_1"),
        ("behavior-ev", "ev_behavior_mvp_case_001_1"),
    ],
)
def test_non_image_evidence_unsupported(
    gateway, evidence_gateway, batch_id: str, evidence_id: str
) -> None:
    _import_batch(gateway, batch_id=batch_id)
    with pytest.raises(UnsupportedMediaTypeError) as exc:
        evidence_gateway.get_evidence_content(batch_id, "mvp_case_001", evidence_id)
    assert exc.value.code == "UNSUPPORTED_MEDIA_TYPE"
    assert exc.value.object_id == evidence_id


def test_no_cross_case_read_within_batch(gateway, evidence_gateway) -> None:
    batch_id = _import_batch(gateway, batch_id="cross-case")
    with pytest.raises(EvidenceNotFoundError):
        evidence_gateway.get_evidence_content(
            batch_id, "mvp_case_001", "ev_image_mvp_case_002"
        )


def test_no_cross_batch_read(gateway, evidence_gateway) -> None:
    _import_batch(gateway, batch_id="alpha", case_ids=("mvp_case_001",))
    _import_batch(gateway, batch_id="beta", case_ids=("mvp_case_002",))
    # beta 的案例在 alpha 批次中不存在
    with pytest.raises(EvidenceNotFoundError):
        evidence_gateway.get_evidence_content(
            "alpha", "mvp_case_002", "ev_image_mvp_case_002"
        )
    # alpha 自己的证据仍可读
    content = evidence_gateway.get_evidence_content(
        "alpha", "mvp_case_001", "ev_image_mvp_case_001"
    )
    assert content.content == JPEG_BYTES


# ---------- 路径与哈希安全 ----------

@pytest.mark.parametrize(
    ("relative_path",),
    [
        ("../outside.jpg",),
        (".." + chr(92) + "outside.jpg",),
        ("/etc/passwd",),
        ("sub/../../outside.jpg",),
        ("",),
    ],
)
def test_tampered_relative_path_unavailable(
    gateway,
    evidence_gateway,
    engine,
    formal_root,
    relative_path: str,
) -> None:
    batch_id = _import_batch(gateway, batch_id="path")
    _tamper_evidence(
        engine,
        batch_id=batch_id,
        case_id="mvp_case_001",
        evidence_id="ev_image_mvp_case_001",
        relative_path=relative_path,
    )
    with pytest.raises(EvidenceNotFoundError) as exc:
        evidence_gateway.get_evidence_content(
            batch_id, "mvp_case_001", "ev_image_mvp_case_001"
        )
    assert exc.value.message == "证据内容不可用"
    assert str(formal_root) not in exc.value.message


def test_deleted_file_unavailable(
    gateway, evidence_gateway, engine, formal_root
) -> None:
    batch_id = _import_batch(gateway, batch_id="deleted")
    file_path, _ = _evidence_file(
        engine,
        formal_root,
        batch_id=batch_id,
        case_id="mvp_case_001",
        evidence_id="ev_image_mvp_case_001",
    )
    file_path.unlink()
    with pytest.raises(EvidenceNotFoundError):
        evidence_gateway.get_evidence_content(
            batch_id, "mvp_case_001", "ev_image_mvp_case_001"
        )


def test_replaced_file_bytes_unavailable(
    gateway, evidence_gateway, engine, formal_root
) -> None:
    batch_id = _import_batch(gateway, batch_id="replaced")
    file_path, _ = _evidence_file(
        engine,
        formal_root,
        batch_id=batch_id,
        case_id="mvp_case_001",
        evidence_id="ev_image_mvp_case_001",
    )
    file_path.write_bytes(b"tampered file bytes")
    with pytest.raises(EvidenceNotFoundError):
        evidence_gateway.get_evidence_content(
            batch_id, "mvp_case_001", "ev_image_mvp_case_001"
        )


def test_tampered_content_hash_unavailable(gateway, evidence_gateway, engine) -> None:
    batch_id = _import_batch(gateway, batch_id="db-hash")
    _tamper_evidence(
        engine,
        batch_id=batch_id,
        case_id="mvp_case_001",
        evidence_id="ev_image_mvp_case_001",
        content_hash="0" * 64,
    )
    with pytest.raises(EvidenceNotFoundError):
        evidence_gateway.get_evidence_content(
            batch_id, "mvp_case_001", "ev_image_mvp_case_001"
        )
