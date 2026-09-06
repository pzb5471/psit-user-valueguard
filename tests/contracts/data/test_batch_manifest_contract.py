"""M1-01 合同验收：批次 manifest 与 checksums（规格第 5.4 节）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.contracts.data import BatchManifest, ChecksumsFile

pytestmark = pytest.mark.task_m1_01

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "runtime" / "contracts"


def load_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


class TestBatchManifest:
    def test_valid_fixture_round_trips(self) -> None:
        manifest = BatchManifest.model_validate_json(
            (FIXTURE_DIR / "valid_batch_manifest.json").read_text(encoding="utf-8")
        )

        reparsed = BatchManifest.model_validate_json(manifest.model_dump_json())

        assert reparsed == manifest
        assert manifest.is_mock is True
        assert manifest.package_type == "DEMO"

    def test_unsorted_case_files_rejected(self) -> None:
        raw = load_fixture("invalid_batch_manifest_unsorted.json")

        with pytest.raises(ValueError, match="升序"):
            BatchManifest.model_validate_json(json.dumps(raw, ensure_ascii=False))

    def test_case_count_mismatch_rejected(self) -> None:
        raw = load_fixture("valid_batch_manifest.json")
        raw["case_count"] = 5

        with pytest.raises(ValueError, match="case_count"):
            BatchManifest.model_validate_json(json.dumps(raw, ensure_ascii=False))

    def test_wrong_package_type_rejected(self) -> None:
        raw = load_fixture("valid_batch_manifest.json")
        raw["package_type"] = "FULL"

        with pytest.raises(ValueError, match="package_type"):
            BatchManifest.model_validate_json(json.dumps(raw, ensure_ascii=False))

    def test_is_mock_false_rejected(self) -> None:
        raw = load_fixture("valid_batch_manifest.json")
        raw["is_mock"] = False

        with pytest.raises(ValueError, match="is_mock"):
            BatchManifest.model_validate_json(json.dumps(raw, ensure_ascii=False))


class TestChecksums:
    def test_valid_fixture_round_trips(self) -> None:
        checksums = ChecksumsFile.model_validate_json(
            (FIXTURE_DIR / "valid_checksums.json").read_text(encoding="utf-8")
        )

        reparsed = ChecksumsFile.model_validate_json(checksums.model_dump_json())

        assert reparsed == checksums

    def test_uppercase_hash_rejected(self) -> None:
        raw = load_fixture("valid_checksums.json")
        raw["manifest.json"] = "A" * 64

        with pytest.raises(ValueError, match="manifest.json"):
            ChecksumsFile.model_validate_json(json.dumps(raw, ensure_ascii=False))

    def test_checksums_containing_itself_rejected(self) -> None:
        raw = load_fixture("valid_checksums.json")
        raw["checksums.json"] = "5" * 64

        with pytest.raises(ValueError, match="checksums.json"):
            ChecksumsFile.model_validate_json(json.dumps(raw, ensure_ascii=False))

    def test_path_traversal_key_rejected(self) -> None:
        raw = load_fixture("valid_checksums.json")
        raw["../cases/case-0001.json"] = "6" * 64

        with pytest.raises(ValueError, match="路径穿越"):
            ChecksumsFile.model_validate_json(json.dumps(raw, ensure_ascii=False))
