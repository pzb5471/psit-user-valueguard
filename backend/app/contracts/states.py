"""共享状态合同：技术实施规格第 7.2 节冻结枚举。

本模块只允许依赖 Python 标准库与 typing（规格第 6 节）；不得导入
FastAPI、SQLAlchemy、Alembic、智谱 SDK 或任何模块实现。

介入等级、原因类别与人工确认结果属于各自消费方的合同，由
M2-01（contracts/analysis.py）与 M3-03（API DTO）另行冻结，不在本文件。
"""

from enum import StrEnum


class CaseStatus(StrEnum):
    """案例业务状态（规格 7.2）。"""

    PENDING_ANALYSIS = "PENDING_ANALYSIS"
    ANALYZING = "ANALYZING"
    PENDING_REVIEW = "PENDING_REVIEW"
    COMPLETED = "COMPLETED"
    PROCESSING_ERROR = "PROCESSING_ERROR"


class BatchStatus(StrEnum):
    """批次业务状态（规格 7.2）。"""

    PENDING_ANALYSIS = "PENDING_ANALYSIS"
    ANALYZING = "ANALYZING"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_ERRORS = "COMPLETED_WITH_ERRORS"


class CaseRunStatus(StrEnum):
    """案例运行内部状态（规格 7.2）。"""

    STARTING = "STARTING"
    PERCEPTION_RUNNING = "PERCEPTION_RUNNING"
    ATTRIBUTION_RUNNING = "ATTRIBUTION_RUNNING"
    STRATEGY_RUNNING = "STRATEGY_RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    INTERRUPTED = "INTERRUPTED"


class BatchRunStatus(StrEnum):
    """批次运行内部状态（规格 7.2）。"""

    STARTING = "STARTING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_ERRORS = "COMPLETED_WITH_ERRORS"
    FAILED = "FAILED"
    INTERRUPTED = "INTERRUPTED"


class TriggerType(StrEnum):
    """运行触发类型（规格 7.2）。"""

    BATCH = "BATCH"
    MANUAL_RERUN = "MANUAL_RERUN"


CASE_STATUS_LABELS: dict[CaseStatus, str] = {
    CaseStatus.PENDING_ANALYSIS: "待分析",
    CaseStatus.ANALYZING: "分析中",
    CaseStatus.PENDING_REVIEW: "待人工确认",
    CaseStatus.COMPLETED: "已完成",
    CaseStatus.PROCESSING_ERROR: "处理异常",
}

BATCH_STATUS_LABELS: dict[BatchStatus, str] = {
    BatchStatus.PENDING_ANALYSIS: "待开始分析",
    BatchStatus.ANALYZING: "分析中",
    BatchStatus.COMPLETED: "分析已完成",
    BatchStatus.COMPLETED_WITH_ERRORS: "分析完成，存在异常",
}
