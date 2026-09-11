"""M1-09 组包集成测试：确定性、双包自校验、合同、泄漏、媒体与清单一致性（规格 5.4—5.6）。

依赖 source_root/dataset 会话夹具：ZIP 产物属运行数据（runtime_data/，不入 Git），
测试在临时目录重建后逐项断言。
"""

import hashlib
import io
import json
import zipfile
from pathlib import Path

from tools.data_preparation.builder import build_dataset

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _zip_entries(data: bytes) -> list[str]:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        return zf.namelist()


def _load_json(data: bytes, name: str) -> dict:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        return json.loads(zf.read(name))


def _case_payloads(data: bytes) -> list[dict]:
    payloads: list[dict] = []
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for name in zf.namelist():
            if name.startswith("cases/") and name.endswith(".json"):
                payloads.append(json.loads(zf.read(name)))
    return payloads


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_deterministic_rebuild_produces_identical_zip(dataset, source_root, tmp_path) -> None:
    second = build_dataset(source_root, tmp_path / "second")
    assert second.mvp_bytes == dataset.mvp_bytes
    assert second.acceptance_bytes == dataset.acceptance_bytes


def test_both_batches_pass_zip_stage(dataset, tmp_path) -> None:
    from app.modules.data.importing.zip_stage import ZipImportStage

    for label, data, expected_cases in (
        ("MVP", dataset.mvp_bytes, 10),
        ("ACCEPTANCE", dataset.acceptance_bytes, 5),
    ):
        result = ZipImportStage(tmp_root=tmp_path).stage(data)
        assert result.ok, "; ".join(r.message for r in result.rejections)
        assert result.case_count == expected_cases


def test_no_answer_leak_in_case_payloads(dataset) -> None:
    from app.modules.data.importing.zip_stage import _leak_findings

    for data in (dataset.mvp_bytes, dataset.acceptance_bytes):
        for payload in _case_payloads(data):
            assert _leak_findings(payload) == []


def test_all_cases_satisfy_case_input_contract(dataset) -> None:
    from app.contracts.data import CaseInput

    all_payloads = [
        payload
        for data in (dataset.mvp_bytes, dataset.acceptance_bytes)
        for payload in _case_payloads(data)
    ]
    assert len(all_payloads) == 15
    for payload in all_payloads:
        CaseInput.model_validate(payload)


def test_zip_structure_has_no_prohibited_entries(dataset) -> None:
    for data in (dataset.mvp_bytes, dataset.acceptance_bytes):
        names = _zip_entries(data)
        assert len(names) == len(set(names))
        assert "manifest.json" in names
        assert "checksums.json" in names
        assert any(name.startswith("cases/") for name in names)
        assert any(name.startswith("assets/") for name in names)
        for name in names:
            assert ".csv" not in name
            assert "service_tasks" not in name
            assert "sealed" not in name
            assert not name.endswith(".zip")


def test_checksums_cover_all_entries_except_self(dataset) -> None:
    for data in (dataset.mvp_bytes, dataset.acceptance_bytes):
        checksums = _load_json(data, "checksums.json")
        expected = {name for name in _zip_entries(data) if name != "checksums.json"}
        assert set(checksums) == expected


def test_manifest_case_files_and_evidence_count(dataset) -> None:
    for data in (dataset.mvp_bytes, dataset.acceptance_bytes):
        manifest = _load_json(data, "manifest.json")
        names = _zip_entries(data)
        for case_file in manifest["case_files"]:
            assert case_file in names
        assert manifest["case_count"] == len(manifest["case_files"])
        total = 0
        for payload in _case_payloads(data):
            evidence = payload["evidence"]
            total += (
                len(evidence["text_items"])
                + len(evidence["image_items"])
                + len(evidence["behavior_items"])
            )
        assert total == manifest["evidence_count"]


def test_asset_magic_matches_extension(dataset) -> None:
    for data in (dataset.mvp_bytes, dataset.acceptance_bytes):
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for name in zf.namelist():
                if not name.startswith("assets/"):
                    continue
                content = zf.read(name)
                if name.endswith(".png"):
                    assert content.startswith(b"\x89PNG\r\n\x1a\n")
                elif name.endswith(".jpg"):
                    assert content.startswith(b"\xff\xd8\xff")
                elif name.endswith(".gif"):
                    assert content.startswith((b"GIF87a", b"GIF89a"))
                else:
                    raise AssertionError(f"未预期的资产扩展名：{name}")


def test_control_case_satisfies_contract(dataset) -> None:
    from app.contracts.data import CaseInput

    control = _read_json(dataset.out_root / "control_case.json")
    model = CaseInput.model_validate(control)
    assert model.batch_id == "control_case_v1"
    assert model.case_id == "control_case_001"
    assert model.customer_value.is_high_value is False


def test_report_matches_packages_and_rfm(dataset) -> None:
    report = _read_json(dataset.out_root / "report.json")
    assert report["packages"]["mvp"]["case_count"] == 10
    assert report["packages"]["acceptance"]["case_count"] == 5
    assert report["packages"]["mvp"]["sha256"] == dataset.mvp_zip_sha256
    assert report["packages"]["acceptance"]["sha256"] == dataset.acceptance_zip_sha256
    assert report["rfm"]["customer_count"] == dataset.rfm.customer_count
    assert report["rfm"]["high_value_count"] == dataset.rfm.high_value_count
    assert report["rfm"]["thresholds"]["r_p75"] == dataset.rfm.thresholds.r_p75_text
    assert report["rfm"]["thresholds"]["m_p80"] == dataset.rfm.thresholds.m_p80_text
    assert report["rfm"]["thresholds"]["m_p50"] == dataset.rfm.thresholds.m_p50_text
    profiles = (dataset.out_root / report["rfm"]["profiles_file"]).read_bytes()
    assert report["rfm"]["profiles_sha256"] == hashlib.sha256(profiles).hexdigest()
    assert len(profiles.splitlines()) == dataset.rfm.customer_count
    source_manifest = _read_json(dataset.out_root / report["source_manifest_file"])
    assert report["source_manifest_sha256"]
    assert source_manifest["files"]


def test_mapping_manifest_covers_all_cases(dataset) -> None:
    mapping = _read_json(dataset.out_root / "mapping_manifest.json")
    assert len(mapping["cases"]) == 15
    mapping_case_ids = {entry["case_id"] for entry in mapping["cases"]}
    payload_case_ids = {
        payload["case_id"]
        for data in (dataset.mvp_bytes, dataset.acceptance_bytes)
        for payload in _case_payloads(data)
    }
    assert payload_case_ids == mapping_case_ids
    assert mapping["control"]["case_id"] == "control_case_001"


def test_sealed_reference_files_cover_all_cases(dataset) -> None:
    sealed_dir = dataset.out_root / "sealed"
    sealed_files = sorted(sealed_dir.glob("*.json"))
    payload_case_ids = {
        payload["case_id"]
        for data in (dataset.mvp_bytes, dataset.acceptance_bytes)
        for payload in _case_payloads(data)
    }
    assert {Path(name).stem for name in sealed_files} == payload_case_ids
    first = json.loads(sealed_files[0].read_text(encoding="utf-8"))
    assert first["case_id"] in payload_case_ids
    assert "source" in first


def test_stage_rejects_broken_zip(tmp_path) -> None:
    from app.modules.data.importing.zip_stage import ZipImportStage

    broken = (FIXTURES_DIR / "failures" / "not_a_zip.zip").read_bytes()
    result = ZipImportStage(tmp_root=tmp_path).stage(broken)
    assert not result.ok
    assert any("无法解析 ZIP" in info.message for info in result.rejections)
