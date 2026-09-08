"""M1-03 媒体与答案泄漏测试：媒体格式/魔数、UPLOAD_TOO_LARGE 与答案泄漏扫描。

对应技术实施规格 5.4：递归拒绝 mood/reason/solution/key_answer 等答案字段与
user_address/database 未脱敏字段；重复 first_query 文本同样拒绝。媒体只接受
JPG/JPEG、PNG、GIF（规格 5.6），扩展名/声明的 media_type/内容魔数三者必须一致。
泄漏扫描先于 CaseInput 合同校验，因此泄漏字段即使被 extra="forbid" 也会先报
ANSWER_LEAKAGE_DETECTED（M1-03 验收：报告不含客户正文）。
"""

from __future__ import annotations

import hashlib

import pytest
from zip_fixtures import (
    GIF_BYTES,
    PNG_BYTES,
    make_case,
    make_entries,
    make_zip,
)

from app.modules.data.importing.errors import ImportRejectionCode, ImportStage
from app.modules.data.importing.zip_stage import ZipImportStage


def _codes(result) -> set[str]:
    return {r.code.value for r in result.rejections}


def _messages(result) -> list[str]:
    return [r.message for r in result.rejections]


# ---------- 媒体：合法格式必须通过（规格 5.6 只接受 JPG/JPEG、PNG、GIF） ----------

@pytest.mark.parametrize(
    ("suffix", "media_type", "image_bytes"),
    (
        (".png", "image/png", PNG_BYTES),
        (".gif", "image/gif", GIF_BYTES),
    ),
)
def test_supported_media_passes(
    stage, suffix: str, media_type: str, image_bytes: bytes
) -> None:
    # 案例 JSON 的路径/媒体类型/内容哈希必须与包内图片文件保持一致。
    def builder(case_id: str) -> dict:
        return make_case(
            case_id,
            image_suffix=suffix,
            media_type=media_type,
            image_bytes=image_bytes,
        )

    result = stage.stage(
        make_zip(
            make_entries(
                case_builder=builder,
                image_suffix=suffix,
                image_bytes=image_bytes,
            )
        )
    )
    assert result.ok
    assert result.rejections == ()


@pytest.mark.parametrize("suffix", (".bmp", ".txt"))
def test_unsupported_extension_rejected(stage, suffix: str) -> None:
    # 扩展名不在支持集合内：即使内容与 media_type 都是 JPEG 也被拒。
    def builder(case_id: str) -> dict:
        return make_case(case_id, image_suffix=suffix)

    result = stage.stage(
        make_zip(
            make_entries(
                case_builder=builder,
                image_suffix=suffix,
                image_bytes=b"\xff\xd8\xff\xd9",
            )
        )
    )
    assert not result.ok
    assert ImportRejectionCode.UNSUPPORTED_MEDIA_TYPE.value in _codes(result)
    assert any(r.stage == ImportStage.MEDIA for r in result.rejections)


def test_media_magic_mismatch_rejected(stage) -> None:
    # 扩展名与 media_type 都声明为 JPEG，但内容魔数不是图片。
    result = stage.stage(
        make_zip(make_entries(image_bytes=b"not an image at all"))
    )
    assert not result.ok
    assert ImportRejectionCode.UNSUPPORTED_MEDIA_TYPE.value in _codes(result)
    messages = _messages(result)
    assert any("魔数" in m for m in messages)
    assert any(r.stage == ImportStage.MEDIA for r in result.rejections)


def test_media_type_not_in_enum_rejected_at_case_contract(stage) -> None:
    # media_type="text/plain" 不是 ImageMediaType 枚举值，先被 CaseInput 合同拒绝。
    def builder(case_id: str) -> dict:
        return make_case(case_id, media_type="text/plain")

    result = stage.stage(make_zip(make_entries(case_builder=builder)))
    assert not result.ok
    assert any(
        r.stage == ImportStage.CASE_CONTRACT
        and r.code == ImportRejectionCode.INPUT_CONTRACT_INVALID
        for r in result.rejections
    )


# ---------- 答案泄漏：递归扫描，报告含字段名但不含泄漏正文 ----------

@pytest.mark.parametrize(
    ("loc", "key", "secret"),
    (
        ((), "key_answer", "TOP_SECRET_ANSWER_42"),
        (("evidence", "text_items", 0), "mood", "angry_secret_mood"),
        (("customer",), "user_address", "NO_ADDRESS_LEAK_42"),
        (("customer_value",), "database", "SECRET_DB_HANDLE"),
    ),
)
def test_answer_leakage_keys_rejected(
    stage, loc: tuple[object, ...], key: str, secret: str
) -> None:
    def builder(case_id: str) -> dict:
        payload = make_case(case_id)
        node: dict = payload
        for part in loc:
            node = node[part]
        node[key] = secret
        return payload

    result = stage.stage(make_zip(make_entries(case_builder=builder)))
    assert not result.ok
    assert _codes(result) == {
        ImportRejectionCode.ANSWER_LEAKAGE_DETECTED.value
    }
    joined = "；".join(_messages(result))
    assert key in joined
    assert secret not in joined


def test_duplicate_first_query_rejected(stage) -> None:
    def builder(case_id: str) -> dict:
        payload = make_case(case_id)
        payload["provenance"]["first_query"] = "客户您好，请问有什么可以帮您？"
        payload["customer_value"]["first_query"] = "客户您好，请问有什么可以帮您？"
        return payload

    result = stage.stage(make_zip(make_entries(case_builder=builder)))
    assert not result.ok
    assert ImportRejectionCode.ANSWER_LEAKAGE_DETECTED.value in _codes(result)
    joined = "；".join(_messages(result))
    assert "重复 first_query" in joined
    assert "请问有什么可以帮您" not in joined


@pytest.mark.parametrize("secret", ("请联系 13800000000", "请访问 https://example.test/order"))
def test_unredacted_text_content_rejected(stage, secret: str) -> None:
    def builder(case_id: str) -> dict:
        payload = make_case(case_id)
        payload["evidence"]["text_items"][0]["text"] = secret
        payload["evidence"]["text_items"][0]["content_hash"] = hashlib.sha256(
            secret.encode()
        ).hexdigest()
        return payload

    result = stage.stage(make_zip(make_entries(case_builder=builder)))
    assert not result.ok
    assert ImportRejectionCode.ANSWER_LEAKAGE_DETECTED.value in _codes(result)
    assert secret not in "；".join(_messages(result))


# ---------- 上传大小上限（ADR-0055 占位值可参数化） ----------

def test_upload_too_large_rejected(tmp_root) -> None:
    stage = ZipImportStage(tmp_root=tmp_root, max_zip_bytes=10)
    result = stage.stage(make_zip(make_entries()))
    assert not result.ok
    assert len(result.rejections) == 1
    rejection = result.rejections[0]
    assert rejection.code == ImportRejectionCode.UPLOAD_TOO_LARGE
    assert rejection.stage == ImportStage.ZIP_STRUCTURE
    assert rejection.object_id == "upload.zip"
