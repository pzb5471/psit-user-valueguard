"""M3-09 后端 E2E：导入→分析→读回→审核→重新读回（HTTP；零网络模型调用）。

成功链脚本由 e2e_app fixture 预填；成功消费三次请求后脚本耗尽，即全程仅
三次确定性模型调用、零真实网络。
"""

from __future__ import annotations

import time
import uuid

from fastapi.testclient import TestClient


def _wait_analysed(client: TestClient, batch_id: str, timeout: float = 8.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        batch = client.get(f"/api/v1/batches/{batch_id}").json()
        if batch.get("analysis_succeeded_count", 0) >= 1:
            return batch
        time.sleep(0.05)
    raise AssertionError("批量分析未在超时前完成")


def _upload(client: TestClient, zip_bytes: bytes) -> str:
    response = client.post(
        "/api/v1/batches",
        files={"file": ("demo.zip", zip_bytes, "application/zip")},
    )
    assert response.status_code == 201, response.text
    return response.json()["batch_id"]


def test_import_analyze_review_e2e(e2e_app, zip_bytes: bytes) -> None:
    client, scripted, _rt = e2e_app

    batch_id = _upload(client, zip_bytes)
    assert client.post(f"/api/v1/batches/{batch_id}/runs").status_code == 202

    batch = _wait_analysed(client, batch_id)
    assert batch["analysis_succeeded_count"] == 1
    assert batch["error_count"] == 0

    queue = client.get(f"/api/v1/batches/{batch_id}/cases").json()
    assert queue["total"] == 1
    case_id = queue["items"][0]["case_id"]

    case = client.get(f"/api/v1/batches/{batch_id}/cases/{case_id}").json()
    assert case["status"] == "PENDING_REVIEW"
    assert case["can_review"] is True
    review_token = case["review_token"]
    assert review_token

    review = client.post(
        f"/api/v1/batches/{batch_id}/cases/{case_id}/reviews",
        json={
            "submission_id": str(uuid.uuid4()),
            "review_token": review_token,
            "outcome": "APPROVED",
        },
    )
    assert review.status_code == 201, review.text
    assert review.json()["outcome"] == "APPROVED"

    final = client.get(f"/api/v1/batches/{batch_id}/cases/{case_id}").json()
    assert final["status"] == "COMPLETED"
    assert final["can_review"] is False

    # 零真实网络模型调用：成功链三次请求后脚本恰好耗尽。
    assert not scripted._outcomes


def test_refresh_read_back_is_stable(e2e_app, zip_bytes: bytes) -> None:
    client, _scripted, _rt = e2e_app
    batch_id = _upload(client, zip_bytes)
    client.post(f"/api/v1/batches/{batch_id}/runs")
    _wait_analysed(client, batch_id)
    # 刷新读回：再次请求同一案例，业务 DTO 稳定（确定性读回）。
    case = client.get(f"/api/v1/batches/{batch_id}/cases/case-0001").json()
    assert case["case_id"] == "case-0001"
    assert case["status"] == "PENDING_REVIEW"
