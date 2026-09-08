"""M3-04 查询接口测试：批次/队列列表、详情、筛选分页、404 与响应白名单。"""

from __future__ import annotations

from fakes import make_detail, make_queue_item, make_workspace


def test_list_batches_pagination(client, query) -> None:
    query.batches = [
        make_workspace(f"b{i}", case_count=i) for i in range(1, 4)
    ]
    response = client.get("/api/v1/batches", params={"limit": 2, "offset": 1})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2
    assert [item["batch_id"] for item in body["items"]] == ["b2", "b3"]
    assert query.last_list_batches_args == (2, 1)


def test_get_batch_detail(client, query) -> None:
    query.batches = [make_workspace("b1", case_count=5, evidence_count=9)]
    response = client.get("/api/v1/batches/b1")
    assert response.status_code == 200
    body = response.json()
    assert body["batch_id"] == "b1"
    assert body["case_count"] == 5
    assert body["evidence_count"] == 9


def test_list_cases_filter_and_pagination(client, query) -> None:
    query.queue = [
        make_queue_item("c1", status="PENDING_ANALYSIS", level="MUST_INTERVENE"),
        make_queue_item("c2", status="PENDING_REVIEW", level="SHOULD_INTERVENE"),
        make_queue_item("c3", status="PENDING_ANALYSIS", level="MUST_INTERVENE"),
    ]
    response = client.get(
        "/api/v1/batches/b1/cases",
        params={"status": "PENDING_ANALYSIS", "limit": 2, "offset": 0},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert [item["case_id"] for item in body["items"]] == ["c1", "c3"]
    assert query.last_list_cases_args == ("PENDING_ANALYSIS", None, 2, 0)


def test_get_case_detail(client, query) -> None:
    query.detail = make_detail()
    response = client.get("/api/v1/batches/b1/cases/c1")
    assert response.status_code == 200
    body = response.json()
    assert body["case_id"] == "c1"
    assert body["is_high_value"] is True
    assert body["is_mock"] is True


def test_missing_batch_404(client, query) -> None:
    query.missing_batch = True
    response = client.get("/api/v1/batches/nope")
    assert response.status_code == 404
    assert response.json()["code"] == "RESOURCE_NOT_FOUND"


def test_missing_case_404(client, query) -> None:
    query.detail = make_detail(case_id="c1")
    response = client.get("/api/v1/batches/b1/cases/missing")
    assert response.status_code == 404
    assert response.json()["code"] == "RESOURCE_NOT_FOUND"
    assert response.json()["object_type"] == "case"


def test_batch_response_stays_in_whitelist(client, query) -> None:
    query.batches = [make_workspace("b1", case_count=2)]
    response = client.get("/api/v1/batches/b1")
    body = response.json()
    assert set(body) == {
        "batch_id",
        "source_filename",
        "is_mock",
        "status",
        "case_count",
        "evidence_count",
        "analysis_succeeded_count",
        "error_count",
        "imported_at",
        "can_start_analysis",
    }
    assert "analysis_unavailable_message" not in body  # 可选字段省略
    for forbidden in ("batch_run_id", "case_run_id", "data_version", "file_path"):
        assert forbidden not in body


def test_case_detail_response_stays_in_whitelist(client, query) -> None:
    query.detail = make_detail()
    body = client.get("/api/v1/batches/b1/cases/c1").json()
    assert set(body) == {
        "batch_id",
        "case_id",
        "customer_display_id",
        "is_high_value",
        "customer_value_summary",
        "status",
        "is_mock",
        "can_rerun",
        "can_review",
    }
    for forbidden in (
        "review_token",
        "processing_error",
        "batch_run_id",
        "data_version",
        "content_hash",
    ):
        assert forbidden not in body
