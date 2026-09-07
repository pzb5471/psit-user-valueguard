"""M3-05 案例执行结果：完整发布、单例失败隔离、输入缺失失败。"""

from __future__ import annotations

from run_fakes import make_failure, make_queue, make_success, make_workspace


def test_success_publishes_complete_result(
    run_store, engine, run_query, service_factory
) -> None:
    run_query.workspace = make_workspace("b1", case_count=1)
    run_query.queue = make_queue("b1", case_ids=["c1"])
    engine.outcomes = {"c1": make_success("c1")}
    service = service_factory()
    service.start_batch_run("b1")
    service.close()
    published = [c for c in run_store.calls if c.startswith("publish:")]
    assert len(published) == 1
    assert published[0] == "publish:1:MUST_INTERVENE"
    assert any(c.startswith("finish:") and "COMPLETED" in c for c in run_store.calls)


def test_singleton_failure_isolation(
    run_store, engine, run_query, service_factory
) -> None:
    """一个案例失败不影响其他案例；批次以 COMPLETED_WITH_ERRORS 结束。"""
    run_query.workspace = make_workspace("b1", case_count=2)
    run_query.queue = make_queue("b1", case_ids=["c1", "c2"])
    engine.outcomes = {"c1": make_success("c1"), "c2": make_failure("c2")}
    service = service_factory()
    service.start_batch_run("b1")
    service.close()
    assert any(c.startswith("publish:") for c in run_store.calls)
    assert any(c.startswith("failure:") and "MODEL_TIMEOUT" in c for c in run_store.calls)
    assert any(
        c.startswith("finish:") and "COMPLETED_WITH_ERRORS" in c for c in run_store.calls
    )


def test_missing_case_input_records_input_error(
    run_store, engine, run_query, service_factory
) -> None:
    run_query.workspace = make_workspace("b1", case_count=1)
    run_query.queue = make_queue("b1", case_ids=["c1"])
    run_query.missing = {"c1"}
    service = service_factory()
    service.start_batch_run("b1")
    service.close()
    assert any(
        c.startswith("failure:") and "INPUT_CONTRACT_INVALID" in c
        for c in run_store.calls
    )
