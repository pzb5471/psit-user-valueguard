"""M1-02：九表逻辑 Schema 的 SQLAlchemy 模型（技术实施规格第 11.1 节；ADR-0036）。

本文件是 M1 数据存储的唯一 Schema 定义，供 Alembic 初始迁移与后续 M1 数据卡引用。

按规格 11.1 / ADR-0036 冻结：
- 九张业务表、全部独立列、外键与唯一性；
- 案例/批次/运行状态、触发类型与介入等级、人工确认结果由 Python 枚举和
  数据库 CHECK 共同约束；
- 全系统最多一个活动 batch_run、同一案例最多一个活动 case_run 由 SQLite
  部分唯一索引在数据库层强制（规格 10.1：数据库唯一约束是最终保护）。

不在本文件冻结：字符串长度、索引名称、ORM 类名与迁移文件名（规格 11.1）。
介入等级与人工确认结果尚不属于共享状态合同（states.py 声明由 M2-01/M3-03
另行冻结），本卡按规格 7.2 在此本地冻结同名枚举，仅供 Schema 约束使用；
六个业务原因存储于 JSON 列，不做数据库枚举。
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    literal_column,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.contracts.states import (
    BatchRunStatus,
    BatchStatus,
    CaseRunStatus,
    CaseStatus,
    TriggerType,
)

_ACTIVE_BATCH_RUN_STATUSES = (
    BatchRunStatus.STARTING.value,
    BatchRunStatus.RUNNING.value,
)
_ACTIVE_CASE_RUN_STATUSES = (
    CaseRunStatus.STARTING.value,
    CaseRunStatus.PERCEPTION_RUNNING.value,
    CaseRunStatus.ATTRIBUTION_RUNNING.value,
    CaseRunStatus.STRATEGY_RUNNING.value,
)

_BATCH_RUN_ACTIVE_WHERE = text(
    "status IN (" + ", ".join(repr(value) for value in _ACTIVE_BATCH_RUN_STATUSES) + ")"
)
_CASE_RUN_ACTIVE_WHERE = text(
    "status IN (" + ", ".join(repr(value) for value in _ACTIVE_CASE_RUN_STATUSES) + ")"
)


class InterventionLevel(StrEnum):
    """介入等级（规格 7.2）：本地 Schema 枚举，按冻结值约束数据库。"""

    MUST_INTERVENE = "MUST_INTERVENE"
    SHOULD_INTERVENE = "SHOULD_INTERVENE"
    NO_IMMEDIATE_INTERVENTION = "NO_IMMEDIATE_INTERVENTION"


class ReviewOutcome(StrEnum):
    """人工确认结果（规格 7.2）：本地 Schema 枚举，按冻结值约束数据库。"""

    APPROVED = "APPROVED"
    MODIFIED_AND_APPROVED = "MODIFIED_AND_APPROVED"
    REJECTED_WITH_JUDGMENT = "REJECTED_WITH_JUDGMENT"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


def _enum_column(enum_cls: type[StrEnum], *, constraint_name: str) -> Enum:
    """冻结枚举列：存储枚举值，由 Python 校验与数据库 CHECK 共同约束（ADR-0036）。

    SQLite 没有原生 ENUM；native_enum=False 时 SQLAlchemy 为每一列生成
    CHECK (column IN (...)) 约束，约束名取 constraint_name。
    """
    return Enum(
        enum_cls,
        name=constraint_name,
        values_callable=lambda cls: [member.value for member in cls],
        native_enum=False,
        validate_strings=True,
        create_constraint=True,
    )


class Base(DeclarativeBase):
    """M1 数据存储 Schema 基类。"""


class DataVersion(Base):
    """data_versions：数据版本与组包追溯信息（规格 11.1）。"""

    __tablename__ = "data_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    data_version: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    source_snapshot_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    source_manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    provenance_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Batch(Base):
    """batches：批次当前投影与导入信息（规格 11.1；ADR-0079）。"""

    __tablename__ = "batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    data_version_id: Mapped[int] = mapped_column(
        ForeignKey("data_versions.id"), nullable=False
    )
    schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    package_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    package_relative_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    status: Mapped[BatchStatus] = mapped_column(
        _enum_column(BatchStatus, constraint_name="batches_status"), nullable=False
    )
    case_count: Mapped[int] = mapped_column(Integer, nullable=False)
    analysis_succeeded_count: Mapped[int] = mapped_column(Integer, nullable=False)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False)
    current_batch_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("batch_runs.id"), nullable=True
    )
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Case(Base):
    """cases：案例当前投影与业务结果（规格 11.1；case_id 在批次内唯一）。"""

    __tablename__ = "cases"
    __table_args__ = (
        UniqueConstraint("batch_id", "case_id", name="uq_cases_batch_id_case_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id"), nullable=False)
    case_id: Mapped[str] = mapped_column(String(128), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    case_input_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    customer_display_id: Mapped[str] = mapped_column(String(255), nullable=False)
    is_high_value: Mapped[bool] = mapped_column(Boolean, nullable=False)
    status: Mapped[CaseStatus] = mapped_column(
        _enum_column(CaseStatus, constraint_name="cases_status"), nullable=False
    )
    system_intervention_level: Mapped[InterventionLevel | None] = mapped_column(
        _enum_column(
            InterventionLevel, constraint_name="cases_system_intervention_level"
        ),
        nullable=True,
    )
    final_intervention_level: Mapped[InterventionLevel | None] = mapped_column(
        _enum_column(InterventionLevel, constraint_name="cases_final_intervention_level"),
        nullable=True,
    )
    current_case_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("case_runs.id"), nullable=True
    )
    current_review_id: Mapped[int | None] = mapped_column(
        ForeignKey("reviews.id"), nullable=True
    )
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Evidence(Base):
    """evidence：案例证据（规格 11.1；evidence_id 在案例内唯一，图片不存 BLOB）。"""

    __tablename__ = "evidence"
    __table_args__ = (
        UniqueConstraint("case_id", "evidence_id", name="uq_evidence_case_id_evidence_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), nullable=False)
    evidence_id: Mapped[str] = mapped_column(String(128), nullable=False)
    modality: Mapped[str] = mapped_column(String(32), nullable=False)
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    identity: Mapped[str] = mapped_column(String(128), nullable=False)
    relation_identity: Mapped[str] = mapped_column(String(128), nullable=False)
    source_ref_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    occurred_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    relative_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    media_type: Mapped[str] = mapped_column(String(128), nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class BatchRun(Base):
    """batch_runs：首次批量分析运行历史（规格 10.3、11.1；run_id 全局唯一）。

    全系统最多一个活动（STARTING/RUNNING）batch_run，由 SQLite 部分唯一索引强制。
    """

    __tablename__ = "batch_runs"
    __table_args__ = (
        Index(
            "uq_batch_runs_one_active",
            literal_column("1"),
            unique=True,
            sqlite_where=_BATCH_RUN_ACTIVE_WHERE,
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id"), nullable=False)
    status: Mapped[BatchRunStatus] = mapped_column(
        _enum_column(BatchRunStatus, constraint_name="batch_runs_status"), nullable=False
    )
    total_case_count: Mapped[int] = mapped_column(Integer, nullable=False)
    analysis_succeeded_count: Mapped[int] = mapped_column(Integer, nullable=False)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CaseRun(Base):
    """case_runs：案例运行历史（规格 10.2、11.1；run_id 全局唯一，只追加不覆盖）。

    同一案例最多一个活动（STARTING/PERCEPTION_RUNNING/ATTRIBUTION_RUNNING/
    STRATEGY_RUNNING）case_run，由 SQLite 部分唯一索引强制；MANUAL_RERUN 不创建伪
    批次运行，因此 batch_run_id 允许为空。
    """

    __tablename__ = "case_runs"
    __table_args__ = (
        Index(
            "uq_case_runs_one_active_per_case",
            "case_id",
            unique=True,
            sqlite_where=_CASE_RUN_ACTIVE_WHERE,
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), nullable=False)
    batch_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("batch_runs.id"), nullable=True
    )
    previous_case_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("case_runs.id"), nullable=True
    )
    trigger_type: Mapped[TriggerType] = mapped_column(
        _enum_column(TriggerType, constraint_name="case_runs_trigger_type"), nullable=False
    )
    status: Mapped[CaseRunStatus] = mapped_column(
        _enum_column(CaseRunStatus, constraint_name="case_runs_status"), nullable=False
    )
    current_stage: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_stage: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_detail_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class StageResult(Base):
    """stage_results：阶段最终合格结果（规格 11.2；同一 case_run+stage_name 唯一）。"""

    __tablename__ = "stage_results"
    __table_args__ = (
        UniqueConstraint(
            "case_run_id", "stage_name", name="uq_stage_results_case_run_id_stage_name"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_run_id: Mapped[int] = mapped_column(ForeignKey("case_runs.id"), nullable=False)
    stage_name: Mapped[str] = mapped_column(String(64), nullable=False)
    contract_version: Mapped[str] = mapped_column(String(64), nullable=False)
    result_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    result_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ModelCall(Base):
    """model_calls：模型调用明细（规格 11.1/11.2；call_id 全局唯一，只追加不覆盖）。

    修复与重试过程保存在这里；供应商实际返回的可用 Token 计数为可选列
    （名称不冻结，语义为可选 Token 计数，规格第 9.2 节）。
    """

    __tablename__ = "model_calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    call_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    case_run_id: Mapped[int] = mapped_column(ForeignKey("case_runs.id"), nullable=False)
    stage_name: Mapped[str] = mapped_column(String(64), nullable=False)
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    request_manifest_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    response_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prompt_token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Review(Base):
    """reviews：正式人工确认结果（规格 11.1；review_id/submission_id 全局唯一）。

    v1 每个案例最多一份正式人工确认（唯一约束 case_id）；系统原结果通过
    case_run_id 引用 stage_results，不在本表复制第二份决策包（规格第 8 节）。
    """

    __tablename__ = "reviews"
    __table_args__ = (UniqueConstraint("case_id", name="uq_reviews_case_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    review_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    submission_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), nullable=False)
    case_run_id: Mapped[int] = mapped_column(ForeignKey("case_runs.id"), nullable=False)
    outcome: Mapped[ReviewOutcome] = mapped_column(
        _enum_column(ReviewOutcome, constraint_name="reviews_outcome"), nullable=False
    )
    final_intervention_level: Mapped[InterventionLevel | None] = mapped_column(
        _enum_column(InterventionLevel, constraint_name="reviews_final_intervention_level"),
        nullable=True,
    )
    final_cause_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    final_actions_json: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
