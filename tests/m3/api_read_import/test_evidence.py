"""M3-04 证据接口测试：受控图片流、归属、404/415 映射与响应头。"""

from __future__ import annotations

from fakes import hash_bytes

from app.modules.data.evidence.gateway import EvidenceContent


def make_image_content(png: bytes = b"\x89PNG\r\n\x1a\nfakepng") -> EvidenceContent:
    return EvidenceContent(
        filename="receipt.png",
        media_type="image/png",
        content=png,
        content_hash=hash_bytes(png),
    )


def test_evidence_returns_byte_stream_and_type(client, evidence) -> None:
    png = b"\x89PNG\r\n\x1a\nfakepng"
    evidence.content = make_image_content(png)
    response = client.get("/api/v1/batches/b1/cases/c1/evidence/e1/content")
    assert response.status_code == 200
    assert response.content == png
    assert response.headers["content-type"] == "image/png"
    assert "receipt.png" in response.headers["content-disposition"]
    assert response.headers["x-content-type-options"] == "nosniff"
    assert evidence.calls == [("b1", "c1", "e1")]


def test_evidence_scope_enforced_by_fake(client, evidence) -> None:
    evidence.content = make_image_content()
    # 任意请求都按 Fake 记录的 (batch, case, evidence) 归属返回，不泄漏其他对象
    response = client.get("/api/v1/batches/b1/cases/c1/evidence/e9/content")
    assert response.status_code == 200
    assert evidence.calls[-1] == ("b1", "c1", "e9")


def test_missing_evidence_404(client, evidence) -> None:
    evidence.not_found = True
    response = client.get("/api/v1/batches/b1/cases/c1/evidence/e1/content")
    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "RESOURCE_NOT_FOUND"
    assert body["object_type"] == "evidence"
    assert body["object_id"] == "e1"
    assert "证据内容不可用" in body["message"]


def test_unsupported_media_415(client, evidence) -> None:
    evidence.unsupported = True
    response = client.get("/api/v1/batches/b1/cases/c1/evidence/e1/content")
    assert response.status_code == 415
    assert response.json()["code"] == "UNSUPPORTED_MEDIA_TYPE"
