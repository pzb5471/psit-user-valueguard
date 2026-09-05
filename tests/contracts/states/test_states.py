"""states.py 合同测试：枚举值与显示文字必须与技术实施规格 7.2 完全一致。"""

from app.contracts.states import (
    BATCH_STATUS_LABELS,
    CASE_STATUS_LABELS,
    BatchRunStatus,
    BatchStatus,
    CaseRunStatus,
    CaseStatus,
    TriggerType,
)


def test_case_status_members() -> None:
    assert {member.value for member in CaseStatus} == {
        "PENDING_ANALYSIS",
        "ANALYZING",
        "PENDING_REVIEW",
        "COMPLETED",
        "PROCESSING_ERROR",
    }


def test_batch_status_members() -> None:
    assert {member.value for member in BatchStatus} == {
        "PENDING_ANALYSIS",
        "ANALYZING",
        "COMPLETED",
        "COMPLETED_WITH_ERRORS",
    }


def test_case_run_status_members() -> None:
    assert {member.value for member in CaseRunStatus} == {
        "STARTING",
        "PERCEPTION_RUNNING",
        "ATTRIBUTION_RUNNING",
        "STRATEGY_RUNNING",
        "SUCCEEDED",
        "FAILED",
        "INTERRUPTED",
    }


def test_batch_run_status_members() -> None:
    assert {member.value for member in BatchRunStatus} == {
        "STARTING",
        "RUNNING",
        "COMPLETED",
        "COMPLETED_WITH_ERRORS",
        "FAILED",
        "INTERRUPTED",
    }


def test_trigger_type_members() -> None:
    assert {member.value for member in TriggerType} == {"BATCH", "MANUAL_RERUN"}


def test_contract_values_equal_member_names() -> None:
    for enum_type in (CaseStatus, BatchStatus, CaseRunStatus, BatchRunStatus, TriggerType):
        for member in enum_type:
            assert member.value == member.name, enum_type.__name__


def test_case_status_labels() -> None:
    assert CASE_STATUS_LABELS == {
        CaseStatus.PENDING_ANALYSIS: "待分析",
        CaseStatus.ANALYZING: "分析中",
        CaseStatus.PENDING_REVIEW: "待人工确认",
        CaseStatus.COMPLETED: "已完成",
        CaseStatus.PROCESSING_ERROR: "处理异常",
    }


def test_batch_status_labels() -> None:
    assert BATCH_STATUS_LABELS == {
        BatchStatus.PENDING_ANALYSIS: "待开始分析",
        BatchStatus.ANALYZING: "分析中",
        BatchStatus.COMPLETED: "分析已完成",
        BatchStatus.COMPLETED_WITH_ERRORS: "分析完成，存在异常",
    }


def test_labels_cover_every_member() -> None:
    assert set(CASE_STATUS_LABELS) == set(CaseStatus)
    assert set(BATCH_STATUS_LABELS) == set(BatchStatus)
