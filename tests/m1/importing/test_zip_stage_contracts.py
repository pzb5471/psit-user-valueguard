"""M1-03 合同与关系测试：manifest/checksums/案例合同、重复 ID、错哈希、超上限。

对应技术实施规格 M1-03 自动验收：重复 ID、错哈希、超 20 案例；错误编号契约
12.4（INVALID_ZIP / INPUT_CONTRACT_INVALID）。金额 float 直通在导入路径同样被
拒绝（M1-01 合同回归）。
"""

from __future__ import annotations

import json

import pytest
from zip_fixtures import JPEG_BYTES, json_bytes, make_case, make_entries, make_zip

from app.modules.data.importing.errors import ImportRejectionCode, ImportStage

BAD_JPEG = JPEG_BYTES[:-1] + b"\x00"  # 保持 JPEG 魔数但内容不同


def _codes(result) -> set[str]:
    return {r.code.value for r in result.rejections}


def _wrapped_case(*, batch_id: str | None = None, data_version: str | None = None):
    def builder(case_id: str) -> dict:
        payload = make_case(case_id)
        if batch_id is not None:
            payload["batch_id"] = batch_id
        if data_version is not None:
            payload["data_version"] = data_version
        return payload

    return builder


def test_manifest_not_json_rejected(stage) -> None:
    entries = make_entries()
    entries["manifest.json"] = b"this is not json"
    result = stage.stage(make_zip(entries))
    assert not result.ok
    assert result.rejections[0].stage == ImportStage.MANIFEST


@pytest.mark.parametrize(
    "override",
    ({"is_mock": False}, {"case_count": 5}, {"package_type": "PROD"}),
)
def test_manifest_contract_violation_rejected(stage, override: dict) -> None:
    result = stage.stage(make_zip(make_entries(manifest_overrides=override)))
    assert not result.ok
    assert ImportRejectionCode.INVALID_ZIP.value in _codes(result)
    assert any(r.stage == ImportStage.MANIFEST for r in result.rejections)


def test_case_files_missing_from_zip_rejected(stage) -> None:
    result = stage.stage(
        make_zip(make_entries(drop=("cases/mvp_case_002.json",)))
    )
    assert not result.ok
    assert any(r.stage == ImportStage.MANIFEST for r in result.rejections)


def test_case_file_not_listed_in_manifest_rejected(stage) -> None:
    extra = {"cases/extra.json": json_bytes(make_case("extra_case"))}
    result = stage.stage(make_zip(make_entries(extra=extra)))
    assert not result.ok
    assert any(r.stage == ImportStage.MANIFEST for r in result.rejections)


def test_over_twenty_cases_rejected(stage) -> None:
    case_ids = tuple(f"mvp_case_{i:03d}" for i in range(1, 22))
    result = stage.stage(make_zip(make_entries(case_ids=case_ids)))
    assert not result.ok
    assert ImportRejectionCode.INVALID_ZIP.value in _codes(result)
    assert any(r.stage == ImportStage.MANIFEST for r in result.rejections)


def test_twenty_one_files_with_short_manifest_rejected(stage) -> None:
    case_ids = tuple(f"mvp_case_{i:03d}" for i in range(1, 22))
    extra = {
        f"cases/{case_id}.json": json_bytes(make_case(case_id))
        for case_id in case_ids
    }
    result = stage.stage(make_zip(make_entries(extra=extra)))
    assert not result.ok
    assert any(r.stage == ImportStage.MANIFEST for r in result.rejections)


def test_wrong_checksum_rejected(stage) -> None:
    entries = make_entries()
    entries["cases/mvp_case_001.json"] = entries["cases/mvp_case_001.json"] + b" "
    result = stage.stage(make_zip(entries))
    assert not result.ok
    assert any(
        r.stage == ImportStage.CHECKSUMS and r.code == ImportRejectionCode.INVALID_ZIP
        for r in result.rejections
    )
    assert any(r.object_id == "cases/mvp_case_001.json" for r in result.rejections)


def test_checksums_missing_key_rejected(stage) -> None:
    entries = make_entries()
    checksums = json.loads(entries["checksums.json"])
    checksums.pop("manifest.json")
    entries["checksums.json"] = json_bytes(checksums)
    result = stage.stage(make_zip(entries))
    assert not result.ok
    assert any(r.stage == ImportStage.CHECKSUMS for r in result.rejections)


def test_checksums_extra_key_rejected(stage) -> None:
    entries = make_entries()
    checksums = json.loads(entries["checksums.json"])
    checksums["notes.txt"] = "0" * 64
    entries["checksums.json"] = json_bytes(checksums)
    result = stage.stage(make_zip(entries))
    assert not result.ok
    assert any(r.stage == ImportStage.CHECKSUMS for r in result.rejections)


def test_checksums_self_entry_rejected(stage) -> None:
    entries = make_entries()
    checksums = json.loads(entries["checksums.json"])
    checksums["checksums.json"] = "0" * 64
    entries["checksums.json"] = json_bytes(checksums)
    result = stage.stage(make_zip(entries))
    assert not result.ok
    assert any(r.stage == ImportStage.CHECKSUMS for r in result.rejections)


def test_invalid_case_json_rejected(stage) -> None:
    entries = make_entries()
    entries["cases/mvp_case_001.json"] = b"not json"
    result = stage.stage(make_zip(entries))
    assert not result.ok
    assert any(
        r.stage == ImportStage.CASE_CONTRACT
        and r.code == ImportRejectionCode.INPUT_CONTRACT_INVALID
        for r in result.rejections
    )


@pytest.mark.parametrize(
    ("loc", "value"),
    (
        (("primary_order", "payment_total"), 918.16),
        (("customer_value", "monetary_total"), 2860.42),
        (("evidence", "behavior_items", 3, "value"), 918.16),
        (("evidence", "text_items", 0, "sequence_no"), "1"),
        (("primary_order", "order_purchase_timestamp"), 1530000000),
    ),
)
def test_case_contract_violation_rejected(stage, loc: tuple, value: object) -> None:
    def builder(case_id: str) -> dict:
        payload = make_case(case_id)
        node: dict = payload
        for part in loc[:-1]:
            node = node[part]
        node[loc[-1]] = value
        return payload

    result = stage.stage(make_zip(make_entries(case_builder=builder)))
    assert not result.ok
    assert any(
        r.stage == ImportStage.CASE_CONTRACT
        and r.code == ImportRejectionCode.INPUT_CONTRACT_INVALID
        for r in result.rejections
    )


def test_duplicate_case_id_rejected(stage) -> None:
    def same_id(file_case_id: str) -> dict:
        # 两个文件共用 mvp_case_001，但保留各自资产路径，避免文件清单先行拒绝。
        payload = make_case("mvp_case_001")
        payload["evidence"]["image_items"][0]["asset_relative_path"] = (
            f"assets/{file_case_id}/scratch_01.jpg"
        )
        return payload

    result = stage.stage(make_zip(make_entries(case_builder=same_id)))
    assert not result.ok
    assert any(
        r.stage == ImportStage.RELATIONSHIP
        and r.code == ImportRejectionCode.INPUT_CONTRACT_INVALID
        and "重复" in r.message
        for r in result.rejections
    )


def test_evidence_count_mismatch_rejected(stage) -> None:
    # checksums 必须与最终字节一致，否则会先在 CHECKSUMS 阶段被拒而走不到关系检查。
    result = stage.stage(
        make_zip(make_entries(manifest_overrides={"evidence_count": 7}))
    )
    assert not result.ok
    assert any(
        r.stage == ImportStage.RELATIONSHIP
        and r.code == ImportRejectionCode.INVALID_ZIP
        for r in result.rejections
    )


def test_batch_id_mismatch_rejected(stage) -> None:
    result = stage.stage(
        make_zip(make_entries(case_builder=_wrapped_case(batch_id="other_batch")))
    )
    assert not result.ok
    assert any(
        r.stage == ImportStage.RELATIONSHIP
        and r.code == ImportRejectionCode.INPUT_CONTRACT_INVALID
        for r in result.rejections
    )


def test_data_version_mismatch_rejected(stage) -> None:
    result = stage.stage(
        make_zip(make_entries(case_builder=_wrapped_case(data_version="other_v")))
    )
    assert not result.ok
    assert any(
        r.stage == ImportStage.RELATIONSHIP
        and r.code == ImportRejectionCode.INPUT_CONTRACT_INVALID
        for r in result.rejections
    )


def test_unreferenced_asset_rejected(stage) -> None:
    extra = {"assets/extra/unknown.jpg": JPEG_BYTES}
    result = stage.stage(make_zip(make_entries(extra=extra)))
    assert not result.ok
    assert any(
        r.stage == ImportStage.RELATIONSHIP
        and r.code == ImportRejectionCode.INVALID_ZIP
        for r in result.rejections
    )


def test_referenced_asset_missing_rejected(stage) -> None:
    result = stage.stage(
        make_zip(make_entries(drop=("assets/mvp_case_002/scratch_01.jpg",)))
    )
    assert not result.ok
    assert any(
        r.stage == ImportStage.RELATIONSHIP
        and r.code == ImportRejectionCode.INVALID_ZIP
        for r in result.rejections
    )


def test_image_evidence_hash_mismatch_rejected(stage) -> None:
    # 魔数仍为 JPEG、checksums 按新字节重算，只有证据 content_hash 与文件不一致。
    result = stage.stage(make_zip(make_entries(image_bytes=BAD_JPEG)))
    assert not result.ok
    assert ImportRejectionCode.INVALID_ZIP.value in _codes(result)
    assert any(
        r.object_id == "assets/mvp_case_001/scratch_01.jpg"
        and r.stage == ImportStage.RELATIONSHIP
        for r in result.rejections
    )
