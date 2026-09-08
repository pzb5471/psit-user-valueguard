"""M1-08 契约测试：ReviewStore 真网关与内存替身执行同一组断言。

规格 12.3/12.4 把 ReviewStore.submit_review 作为数据端口合同：真实实现
（SQLite + Alembic 全量迁移 + BatchImportGateway 导入 + RunStore 发布）与
替身（FakeReviewStore seed_*/advance_case_run 注入等价基线）必须对同一组
输入给出逐字一致的结果与错误码。本文件只通过 harness 方法读写状态，断言
体在两种实现之间完全一致，防止真网关与替身各自漂移。

harness 契约覆盖（规格 12.3 校验顺序）：
- 四种 outcome 合法提交：视图 final_* 落库值优先、缺省值经 stage_results
  回填，案例/批次投影与计数同步（10.3 同源公式）；
- 字段规则负向：缺必填 / APPROVED 禁止 final_* / 非法 outcome →
  REQUEST_VALIDATION_FAILED（422），整体回滚无半写入；
- 幂等：同一 submission_id 重复提交返回同一结果，不新增行；
- 过期运行：重跑后旧 token → STALE_CASE_RESULT、新 token →
  CASE_ALREADY_COMPLETED（409）；
- 错 token → STALE_CASE_RESULT；未知 case_run → RESOURCE_NOT_FOUND（404）。
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from zip_fixtures import make_case, make_entries, make_zip

from app.contracts.states import BatchRunStatus, TriggerType
from app.modules.data.db.models import Batch, Case, Review
from app.modules.data.fakes import FakeReviewStore
from app.modules.data.importing.gateway import BatchImportGateway
from app.modules.data.queries.views import ReviewResultView
from app.modules.data.review_store import (
    CaseAlreadyCompletedError,
    ReviewFieldValidationError,
    ReviewStore,
    ReviewStoreResourceNotFoundError,
    ReviewSubmitInput,
    StaleCaseResultError,
)
from app.modules.data.run_store import (
    COMPLETE_PACKAGE_STAGES,
    RunStore,
    StageResultInput,
)

OCCURRED_AT = datetime(2026, 9, 1, 6, 0, 0, tzinfo=UTC)
DEFAULT_RISK_SUMMARY = "高价值风险待处理"
DEFAULT_PRIORITY_REASON = "高价值客户且商品问题明确"

BACKEND_DIR = Path(__file__).resolve().parents[3] / "backend"
ALEMBIC_INI = BACKEND_DIR / "alembic" / "alembic.ini"


# ---------- 独立临时库与网关（与 tests/m1/review_store/conftest.py 同源） ----------

def _run_migrations(db_path: Path) -> None:
    """在给定 SQLite 文件上执行 alembic upgrade head（PSIT_DB_URL 覆盖默认库）。"""
    cfg = Config(str(ALEMBIC_INI))
    previous = os.environ.get("PSIT_DB_URL")
    os.environ["PSIT_DB_URL"] = f"sqlite:///{db_path.as_posix()}"
    try:
        command.upgrade(cfg, "head")
    finally:
        if previous is None:
            os.environ.pop("PSIT_DB_URL", None)
        else:
            os.environ["PSIT_DB_URL"] = previous


def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:  # pragma: no cover
    """SQLite 默认不强制外键；按规格 11.2 保存规则每次连接显式开启。"""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """每次测试独立的临时 SQLite 文件路径（开始时不存在）。"""
    return tmp_path / "psit.db"


@pytest.fixture
def engine(db_path: Path) -> Iterator[Engine]:
    """已经迁移到 head 并开启外键强制的 SQLite 引擎。"""
    _run_migrations(db_path)
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    event.listen(engine, "connect", _enable_foreign_keys)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def formal_root(tmp_path: Path) -> Path:
    """临时运行数据根；正式批次目录为 formal_root/batches/<batch_id>/<data_version>/。"""
    return tmp_path / "runtime_data"


@pytest.fixture
def tmp_root(tmp_path: Path) -> Path:
    """独立临时导入根（规格 11.3 imports/tmp/）。"""
    return tmp_path / "runtime_data" / "imports" / "tmp"


@pytest.fixture
def gateway(engine: Engine, formal_root: Path, tmp_root: Path) -> BatchImportGateway:
    """注入独立库、独立运行数据根与默认上限的 BatchImportGateway。"""
    return BatchImportGateway(engine=engine, formal_root=formal_root, tmp_root=tmp_root)


@pytest.fixture
def run_store(engine: Engine) -> RunStore:
    """注入独立库的 RunStore（SQLite 版短事务命令网关）。"""
    return RunStore(engine=engine)


@pytest.fixture
def review_store(engine: Engine) -> ReviewStore:
    """注入独立库的 ReviewStore（SQLite 版人工确认短事务命令网关）。"""
    return ReviewStore(engine=engine)


# ---------- 测试构造助手（与 tests/m1/review_store/test_review_store.py 同源） ----------

def _review_token(batch_id: str, case_id: str, run_id: str) -> str:
    """按规格 12.3 文档算法生成 review_token（与实现同源，不 import）。"""
    digest = hashlib.sha256(f"psit-review:{batch_id}:{case_id}:{run_id}".encode())
    return digest.hexdigest()


def _standard_stages(*, case_id: str = "demo_case_001") -> dict[str, dict[str, Any]]:
    """生成 perception/attribution/strategy 三个标准阶段结果（约定键）。"""
    return {
        "perception": {
            "risk_summary": DEFAULT_RISK_SUMMARY,
            "image_observations": [
                {
                    "evidence_id": f"ev_image_{case_id}",
                    "observable_facts": ["商品外观有划痕"],
                }
            ],
        },
        "attribution": {
            "primary_cause": {"cause_category": "PRODUCT_ISSUE", "confidence": 0.9},
            "support_evidence": [],
            "has_evidence_conflict": False,
        },
        "strategy": {
            "intervention_level": "MUST_INTERVENE",
            "priority_reason": DEFAULT_PRIORITY_REASON,
            "actions": [{"action_type": "CUSTOMER_CONTACT", "content": "联系客户"}],
            "communication_points": [{"point": "致歉并说明换货进度"}],
            "execution_note": "已生成沟通要点",
            "has_insufficient_evidence": False,
            "has_modality_failure": False,
            "uncertainty": ["配送时间不确定"],
            "missing_evidence": ["order_delivery_detail"],
        },
    }


def _stage_input(
    stage_name: str,
    *,
    case_id: str = "demo_case_001",
    result_json: dict[str, Any] | None = None,
) -> StageResultInput:
    """构造一份标准阶段结果输入；sha256 与实际 JSON 内容自洽。"""
    payload = _standard_stages(case_id=case_id).get(stage_name)
    if payload is None:
        raise AssertionError(f"未知阶段: {stage_name}")
    content = result_json if result_json is not None else payload
    sha256 = hashlib.sha256(
        json.dumps(content, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return StageResultInput(
        stage_name=stage_name,
        contract_version="decision_package.v1",
        result_json=content,
        result_sha256=sha256,
    )


def _wrapped_case(*, batch_id: str) -> Callable[[str], dict[str, Any]]:
    """改写案例 JSON 的 batch_id，配合 manifest_overrides 导入多批次。"""

    def builder(case_id: str) -> dict[str, Any]:
        payload = make_case(case_id)
        payload["batch_id"] = batch_id
        return payload

    return builder


def _import_batch(
    gateway: BatchImportGateway,
    *,
    batch_id: str,
    case_ids: tuple[str, ...] = ("demo_case_001",),
) -> str:
    """导入一个由 zip_fixtures 构造的完整标准 ZIP，返回 batch_id。"""
    entries = make_entries(
        case_ids=case_ids,
        case_builder=_wrapped_case(batch_id=batch_id),
        manifest_overrides={"batch_id": batch_id},
    )
    result = gateway.import_zip(
        make_zip(entries), source_filename="upload.zip", trace_id=f"trace-{batch_id}"
    )
    assert result.ok, result
    assert result.batch_id == batch_id
    return batch_id


# ---------- harness：同一组断言在 real / fake 上各跑一遍 ----------

@dataclass(frozen=True)
class _ReadyCase:
    """一个可审核基线：案例运行内部 id 与其 review_token。"""

    case_run_id: int
    review_token: str


class _Harness(Protocol):
    """契约测试统一读写接口：real/fake 实现逐字一致的语义。"""

    def ready(self, *, batch_id: str, case_id: str = "demo_case_001") -> _ReadyCase: ...

    def rerun(self, *, batch_id: str, case_id: str, run_id: str) -> _ReadyCase: ...

    def submit(
        self,
        *,
        submission_id: str,
        case_run_id: int,
        review_token: str,
        payload: ReviewSubmitInput,
        occurred_at: datetime | None = None,
    ) -> ReviewResultView: ...

    def review_count(self) -> int: ...

    def review_ids(self) -> list[str]: ...

    def case_snapshot(self, *, batch_id: str, case_id: str) -> dict[str, Any]: ...

    def finish_batch(self, *, batch_id: str) -> None: ...


class _RealHarness:
    """SQLite 全链路实现：BatchImportGateway 导入 → RunStore 发布 → ReviewStore 提交。"""

    def __init__(
        self,
        *,
        engine: Engine,
        gateway: BatchImportGateway,
        run_store: RunStore,
        review_store: ReviewStore,
    ) -> None:
        self._engine = engine
        self._gateway = gateway
        self._run_store = run_store
        self._review_store = review_store

    def _publish(
        self, *, batch_id: str, case_id: str, run_id: str, batch_run_id: str | None
    ) -> _ReadyCase:
        """创建案例运行、记录完整决策包并原子发布（MANUAL_RERUN 无批次运行）。"""
        case_run = self._run_store.create_case_run(
            batch_id=batch_id,
            case_id=case_id,
            run_id=run_id,
            trigger_type=TriggerType.BATCH if batch_run_id else TriggerType.MANUAL_RERUN,
            batch_run_id=batch_run_id,
        )
        for stage_name in COMPLETE_PACKAGE_STAGES:
            self._run_store.record_stage_result(
                case_run_id=case_run.id, stage=_stage_input(stage_name, case_id=case_id)
            )
        self._run_store.publish_complete_result(
            case_run_id=case_run.id,
            final_stage=_stage_input("strategy", case_id=case_id),
            system_intervention_level="MUST_INTERVENE",
        )
        return _ReadyCase(
            case_run_id=case_run.id,
            review_token=_review_token(batch_id, case_id, case_run.run_id),
        )

    def ready(self, *, batch_id: str, case_id: str = "demo_case_001") -> _ReadyCase:
        """导入单案例批次并发布首次完整决策包。"""
        _import_batch(self._gateway, batch_id=batch_id, case_ids=(case_id,))
        batch_run = self._run_store.create_batch_run(
            batch_id=batch_id, run_id=f"{batch_id}-batch-1", total_case_count=1
        )
        return self._publish(
            batch_id=batch_id,
            case_id=case_id,
            run_id=f"{batch_id}-cr-1",
            batch_run_id=batch_run.run_id,
        )

    def rerun(self, *, batch_id: str, case_id: str, run_id: str) -> _ReadyCase:
        """切换当前运行发布新决策包（模拟 RunStore 重跑）。"""
        return self._publish(
            batch_id=batch_id, case_id=case_id, run_id=run_id, batch_run_id=None
        )

    def submit(
        self,
        *,
        submission_id: str,
        case_run_id: int,
        review_token: str,
        payload: ReviewSubmitInput,
        occurred_at: datetime | None = None,
    ) -> ReviewResultView:
        return self._review_store.submit_review(
            submission_id=submission_id,
            case_run_id=case_run_id,
            review_token=review_token,
            payload=payload,
            occurred_at=occurred_at,
        )

    def review_count(self) -> int:
        with Session(self._engine) as session:
            return len(list(session.scalars(select(Review))))

    def review_ids(self) -> list[str]:
        with Session(self._engine) as session:
            return [row.review_id for row in session.scalars(select(Review))]

    def case_snapshot(self, *, batch_id: str, case_id: str) -> dict[str, Any]:
        with Session(self._engine) as session:
            batch = session.scalar(select(Batch).where(Batch.batch_id == batch_id))
            assert batch is not None, batch_id
            case = session.scalar(
                select(Case).where(Case.batch_id == batch.id, Case.case_id == case_id)
            )
            assert case is not None, f"{batch_id}/{case_id}"
            return {
                "status": case.status.value,
                "current_review_id": case.current_review_id,
                "final_intervention_level": (
                    case.final_intervention_level.value
                    if case.final_intervention_level is not None
                    else None
                ),
                "batch_status": batch.status.value,
                "analysis_succeeded_count": batch.analysis_succeeded_count,
                "error_count": batch.error_count,
            }

    def finish_batch(self, *, batch_id: str) -> None:
        """模拟 M3 判定首次分析结束：关闭该批次唯一的批量运行（规格 10.3）。"""
        runs = self._run_store.batch_run_history(batch_id=batch_id)
        assert len(runs) == 1, batch_id
        self._run_store.finish_batch_run(
            batch_run_id=runs[0].id, status=BatchRunStatus.COMPLETED
        )


class _FakeHarness:
    """内存替身实现：FakeReviewStore seed_*/advance_case_run 注入等价基线。"""

    def __init__(self, store: FakeReviewStore) -> None:
        self._store = store

    def _case_internal(self, *, batch_id: str, case_id: str) -> int:
        return self._store._case_by_public[(batch_id, case_id)]

    def _seed_stages(self, *, case_run_id: int, case_id: str) -> None:
        for stage_name, content in _standard_stages(case_id=case_id).items():
            self._store.seed_stage_result(
                case_run_id=case_run_id, stage_name=stage_name, result_json=content
            )

    def ready(self, *, batch_id: str, case_id: str = "demo_case_001") -> _ReadyCase:
        """seed 批次/案例/运行与三阶段结果，等价于 RunStore 发布后基线。"""
        self._store.seed_batch(batch_id=batch_id)
        self._store.seed_case(
            batch_id=batch_id,
            case_id=case_id,
            current_case_run_id=1,
            system_intervention_level="MUST_INTERVENE",
        )
        run_id = f"{batch_id}-cr-1"
        self._store.seed_case_run(
            case_run_id=1,
            run_id=run_id,
            case_internal_id=self._case_internal(batch_id=batch_id, case_id=case_id),
        )
        self._seed_stages(case_run_id=1, case_id=case_id)
        case = self._store._cases[self._case_internal(batch_id=batch_id, case_id=case_id)]
        self._store._refresh_batch_projection(case, datetime.now(UTC))
        return _ReadyCase(
            case_run_id=1, review_token=_review_token(batch_id, case_id, run_id)
        )

    def rerun(self, *, batch_id: str, case_id: str, run_id: str) -> _ReadyCase:
        """advance_case_run 切换当前运行并注入新运行的三阶段结果。"""
        new_run_id = 2
        self._seed_stages(case_run_id=new_run_id, case_id=case_id)
        self._store.advance_case_run(
            batch_id=batch_id,
            case_id=case_id,
            case_run_id=new_run_id,
            run_id=run_id,
        )
        case = self._store._cases[self._case_internal(batch_id=batch_id, case_id=case_id)]
        self._store._refresh_batch_projection(case, datetime.now(UTC))
        return _ReadyCase(
            case_run_id=new_run_id, review_token=_review_token(batch_id, case_id, run_id)
        )

    def submit(
        self,
        *,
        submission_id: str,
        case_run_id: int,
        review_token: str,
        payload: ReviewSubmitInput,
        occurred_at: datetime | None = None,
    ) -> ReviewResultView:
        return self._store.submit_review(
            submission_id=submission_id,
            case_run_id=case_run_id,
            review_token=review_token,
            payload=payload,
            occurred_at=occurred_at,
        )

    def review_count(self) -> int:
        return len(self._store._reviews)

    def review_ids(self) -> list[str]:
        return [row["review_id"] for row in self._store._reviews.values()]

    def case_snapshot(self, *, batch_id: str, case_id: str) -> dict[str, Any]:
        case = self._store._cases[self._case_internal(batch_id=batch_id, case_id=case_id)]
        batch = self._store._batches[case["batch_id_internal"]]
        return {
            "status": case["status"].value,
            "current_review_id": case["current_review_id"],
            "final_intervention_level": (
                case["final_intervention_level"].value
                if case["final_intervention_level"] is not None
                else None
            ),
            "batch_status": batch["status"],
            "analysis_succeeded_count": batch["analysis_succeeded_count"],
            "error_count": batch["error_count"],
        }

    def finish_batch(self, *, batch_id: str) -> None:
        """替身无批量运行生命周期；契约循环场景下为空操作。"""


@pytest.fixture(params=["real", "fake"])
def harness(
    request: pytest.FixtureRequest,
    engine: Engine,
    gateway: BatchImportGateway,
    run_store: RunStore,
    review_store: ReviewStore,
) -> _Harness:
    """同一组断言在真网关与内存替身上各跑一遍。"""
    if request.param == "real":
        return _RealHarness(
            engine=engine,
            gateway=gateway,
            run_store=run_store,
            review_store=review_store,
        )
    return _FakeHarness(store=FakeReviewStore(engine=engine))


# ---------- 载荷 ----------

def _approved_payload() -> ReviewSubmitInput:
    return ReviewSubmitInput(outcome="APPROVED")


def _modified_payload() -> ReviewSubmitInput:
    return ReviewSubmitInput(
        outcome="MODIFIED_AND_APPROVED",
        final_intervention_level="SHOULD_INTERVENE",
        final_cause={"cause_category": "LOGISTICS_FULFILLMENT"},
        final_actions=[{"action_type": "FULFILLMENT_ESCALATION"}],
        review_reason="物流时效问题，需升级履约处理",
        execution_note="已与客户确认补发时间",
    )


def _rejected_payload() -> ReviewSubmitInput:
    return ReviewSubmitInput(
        outcome="REJECTED_WITH_JUDGMENT",
        final_intervention_level="MUST_INTERVENE",
        final_cause={"cause_category": "PRODUCT_ISSUE"},
        final_actions=[
            {"action_type": "CUSTOMER_CONTACT"},
            {"action_type": "REPLACEMENT_RETURN_REFUND_CHECK"},
        ],
        review_reason="商品问题明确，建议换货并联系客户",
    )


def _insufficient_payload() -> ReviewSubmitInput:
    return ReviewSubmitInput(
        outcome="INSUFFICIENT_EVIDENCE",
        review_reason="图片与订单信息不足以判定责任归属",
    )


# ---------- 契约断言 ----------

def test_four_outcomes_submit_persist_and_project(harness: _Harness) -> None:
    scenarios = (
        ("ct-rv1", "ct-approve-001", _approved_payload(), "APPROVED", None),
        (
            "ct-rv2",
            "ct-modify-001",
            _modified_payload(),
            "MODIFIED_AND_APPROVED",
            "SHOULD_INTERVENE",
        ),
        (
            "ct-rv3",
            "ct-reject-001",
            _rejected_payload(),
            "REJECTED_WITH_JUDGMENT",
            "MUST_INTERVENE",
        ),
        ("ct-rv4", "ct-insuff-001", _insufficient_payload(), "INSUFFICIENT_EVIDENCE", None),
    )
    for batch_id, submission_id, payload, expected, final_level in scenarios:
        ready = harness.ready(batch_id=batch_id)
        view = harness.submit(
            submission_id=submission_id,
            case_run_id=ready.case_run_id,
            review_token=ready.review_token,
            payload=payload,
            occurred_at=OCCURRED_AT,
        )
        assert view.outcome == expected
        assert view.created_at == OCCURRED_AT.isoformat()
        assert view.execution_note == (
            "已与客户确认补发时间"
            if expected == "MODIFIED_AND_APPROVED"
            else "已生成沟通要点"
        )
        if expected == "APPROVED":
            assert view.final_intervention_level == "MUST_INTERVENE"
            assert view.final_cause == {
                "cause_category": "PRODUCT_ISSUE",
                "confidence": 0.9,
            }
            assert view.final_actions == [
                {"action_type": "CUSTOMER_CONTACT", "content": "联系客户"}
            ]
            assert view.review_reason is None
        elif expected == "MODIFIED_AND_APPROVED":
            assert view.final_intervention_level == "SHOULD_INTERVENE"
            assert view.final_cause == {"cause_category": "LOGISTICS_FULFILLMENT"}
            assert view.final_actions == [{"action_type": "FULFILLMENT_ESCALATION"}]
            assert view.review_reason == "物流时效问题，需升级履约处理"
        elif expected == "REJECTED_WITH_JUDGMENT":
            assert view.final_intervention_level == "MUST_INTERVENE"
            assert view.final_cause == {"cause_category": "PRODUCT_ISSUE"}
            assert view.final_actions == [
                {"action_type": "CUSTOMER_CONTACT"},
                {"action_type": "REPLACEMENT_RETURN_REFUND_CHECK"},
            ]
            assert view.review_reason == "商品问题明确，建议换货并联系客户"
        else:  # INSUFFICIENT_EVIDENCE
            assert view.final_intervention_level is None
            assert view.final_cause is None
            assert view.final_actions is None
            assert view.review_reason == "图片与订单信息不足以判定责任归属"
        snapshot = harness.case_snapshot(batch_id=batch_id, case_id="demo_case_001")
        assert snapshot["status"] == "COMPLETED"
        assert snapshot["current_review_id"] is not None
        assert snapshot["final_intervention_level"] == final_level
        assert snapshot["batch_status"] == "COMPLETED"
        assert snapshot["analysis_succeeded_count"] == 1
        assert snapshot["error_count"] == 0
        harness.finish_batch(batch_id=batch_id)
    assert harness.review_ids() == [
        f"review-{submission_id}" for _, submission_id, *_ in scenarios
    ]


@pytest.mark.parametrize(
    ("payload", "message_fragment"),
    [
        (ReviewSubmitInput(outcome="MODIFIED_AND_APPROVED"), "final_intervention_level"),
        (
            ReviewSubmitInput(
                outcome="APPROVED",
                final_intervention_level="MUST_INTERVENE",
            ),
            "禁止提供 final_intervention_level",
        ),
        (ReviewSubmitInput(outcome="INSUFFICIENT_EVIDENCE"), "review_reason"),
        (ReviewSubmitInput(outcome="UNKNOWN_OUTCOME"), "outcome"),
    ],
    ids=[
        "modified_missing_level",
        "approved_forbids_final",
        "insufficient_missing_reason",
        "unknown_outcome",
    ],
)
def test_invalid_field_payload_rejected_without_review(
    harness: _Harness, payload: ReviewSubmitInput, message_fragment: str
) -> None:
    batch_id = "ct-inv"
    ready = harness.ready(batch_id=batch_id)
    before = harness.case_snapshot(batch_id=batch_id, case_id="demo_case_001")
    with pytest.raises(ReviewFieldValidationError) as err:
        harness.submit(
            submission_id="ct-inv-sub",
            case_run_id=ready.case_run_id,
            review_token=ready.review_token,
            payload=payload,
        )
    assert err.value.code == "REQUEST_VALIDATION_FAILED"
    assert message_fragment in err.value.message
    assert harness.review_count() == 0
    assert (
        harness.case_snapshot(batch_id=batch_id, case_id="demo_case_001") == before
    )


def test_resubmit_same_submission_id_is_idempotent(harness: _Harness) -> None:
    batch_id = "ct-idem"
    ready = harness.ready(batch_id=batch_id)
    first = harness.submit(
        submission_id="ct-idem-sub",
        case_run_id=ready.case_run_id,
        review_token=ready.review_token,
        payload=_modified_payload(),
        occurred_at=OCCURRED_AT,
    )
    second = harness.submit(
        submission_id="ct-idem-sub",
        case_run_id=ready.case_run_id,
        review_token=ready.review_token,
        payload=_approved_payload(),
        occurred_at=OCCURRED_AT,
    )
    assert second == first
    assert second.created_at == OCCURRED_AT.isoformat()
    assert harness.review_count() == 1
    assert harness.review_ids() == ["review-ct-idem-sub"]


def test_rerun_makes_old_token_stale_and_blocks_new_review(harness: _Harness) -> None:
    batch_id = "ct-stale"
    first = harness.ready(batch_id=batch_id)
    harness.submit(
        submission_id="ct-stale-sub-1",
        case_run_id=first.case_run_id,
        review_token=first.review_token,
        payload=_approved_payload(),
    )
    second = harness.rerun(
        batch_id=batch_id, case_id="demo_case_001", run_id=f"{batch_id}-cr-2"
    )
    with pytest.raises(StaleCaseResultError) as err_1:
        harness.submit(
            submission_id="ct-stale-sub-2",
            case_run_id=first.case_run_id,
            review_token=first.review_token,
            payload=_approved_payload(),
        )
    assert err_1.value.code == "STALE_CASE_RESULT"
    with pytest.raises(CaseAlreadyCompletedError) as err_2:
        harness.submit(
            submission_id="ct-stale-sub-3",
            case_run_id=second.case_run_id,
            review_token=second.review_token,
            payload=_approved_payload(),
        )
    assert err_2.value.code == "CASE_ALREADY_COMPLETED"
    assert harness.review_count() == 1
    snapshot = harness.case_snapshot(batch_id=batch_id, case_id="demo_case_001")
    assert snapshot["current_review_id"] is not None


def test_wrong_token_rejected_as_stale(harness: _Harness) -> None:
    ready = harness.ready(batch_id="ct-tok")
    with pytest.raises(StaleCaseResultError) as err:
        harness.submit(
            submission_id="ct-tok-sub",
            case_run_id=ready.case_run_id,
            review_token="invalid-token",
            payload=_approved_payload(),
        )
    assert err.value.code == "STALE_CASE_RESULT"
    assert harness.review_count() == 0


def test_unknown_case_run_returns_resource_not_found(harness: _Harness) -> None:
    harness.ready(batch_id="ct-nf")
    with pytest.raises(ReviewStoreResourceNotFoundError) as err:
        harness.submit(
            submission_id="ct-nf-sub",
            case_run_id=999_999,
            review_token="irrelevant",
            payload=_approved_payload(),
        )
    assert err.value.code == "RESOURCE_NOT_FOUND"
