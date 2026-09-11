"""M3-04 导入接口测试：201 新导入、200 重复、导入错误映射。"""

from __future__ import annotations

from fakes import make_workspace

from app.modules.data.importing.errors import ImportRejectionCode


def test_new_import_returns_201_and_workspace(client, importer, query) -> None:
    query.batches = [make_workspace("b1", case_count=2, evidence_count=3)]
    response = client.post(
        "/api/v1/batches",
        files={"file": ("mvp.zip", b"zip-content", "application/zip")},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["batch_id"] == "b1"
    assert body["case_count"] == 2
    assert body["evidence_count"] == 3
    assert body["is_mock"] is True
    assert body["status"] == "PENDING_ANALYSIS"
    assert importer.calls[0][1] == "mvp.zip"


def test_duplicate_import_returns_200(client, importer, query) -> None:
    query.batches = [make_workspace("b1", case_count=2)]
    importer.duplicate_bytes = b"same-package"
    response = client.post(
        "/api/v1/batches",
        files={"file": ("same.zip", b"same-package", "application/zip")},
    )
    assert response.status_code == 200
    assert response.json()["batch_id"] == "b1"


def test_import_rejection_maps_413(client, importer) -> None:
    importer.reject_code = ImportRejectionCode.UPLOAD_TOO_LARGE
    response = client.post(
        "/api/v1/batches",
        files={"file": ("large.zip", b"content", "application/zip")},
    )
    assert response.status_code == 413
    assert response.json()["code"] == "UPLOAD_TOO_LARGE"
    assert "detail" not in response.json()


def test_import_rejection_maps_415(client, importer) -> None:
    importer.reject_code = ImportRejectionCode.UNSUPPORTED_MEDIA_TYPE
    response = client.post(
        "/api/v1/batches",
        files={"file": ("bad.zip", b"content", "application/zip")},
    )
    assert response.status_code == 415
    assert response.json()["code"] == "UNSUPPORTED_MEDIA_TYPE"
