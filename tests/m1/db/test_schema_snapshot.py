"""M1-02 九表 Schema 快照测试：模型声明必须与技术实施规格 11.1 / ADR-0036 一致。

本文件是"九表字段快照"的静态面：
- 恰好九张业务表，不允许第十张业务表（任务卡禁止事项）；
- 每张表的独立列、可空性、主键、唯一约束、外键与枚举列冻结；
- 活动 batch_run / 活动 case_run 的部分唯一索引在模型中声明。

字符串长度、索引名称以外的实现细节不冻结；动态面（迁移是否真的建出
这些约束、CHECK 是否生效）见 test_migrations.py 与 test_constraints.py。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.schema import (
    Column,
    ForeignKeyConstraint,
    PrimaryKeyConstraint,
    UniqueConstraint,
)

from app.modules.data.db.models import Base, InterventionLevel, ReviewOutcome

NINE_TABLES = {
    "data_versions",
    "batches",
    "cases",
    "evidence",
    "batch_runs",
    "case_runs",
    "stage_results",
    "model_calls",
    "reviews",
}

# 规格 11.1 / ADR-0036：表 -> 独立列（类型族按列语义冻结；可空性单独断言）。
EXPECTED_TYPES: dict[str, dict[str, str]] = {
    "data_versions": {
        "id": "int",
        "data_version": "str",
        "source_snapshot_ref": "str",
        "source_manifest_sha256": "str",
        "provenance_json": "json",
        "created_at": "datetime",
    },
    "batches": {
        "id": "int",
        "batch_id": "str",
        "data_version_id": "int",
        "schema_version": "str",
        "package_sha256": "str",
        "package_relative_path": "str",
        "status": "enum",
        "case_count": "int",
        "analysis_succeeded_count": "int",
        "error_count": "int",
        "current_batch_run_id": "int",
        "imported_at": "datetime",
        "updated_at": "datetime",
    },
    "cases": {
        "id": "int",
        "batch_id": "int",
        "case_id": "str",
        "schema_version": "str",
        "case_input_json": "json",
        "customer_display_id": "str",
        "is_high_value": "bool",
        "status": "enum",
        "system_intervention_level": "enum",
        "final_intervention_level": "enum",
        "current_case_run_id": "int",
        "current_review_id": "int",
        "imported_at": "datetime",
        "updated_at": "datetime",
    },
    "evidence": {
        "id": "int",
        "case_id": "int",
        "evidence_id": "str",
        "modality": "str",
        "sequence_no": "int",
        "identity": "str",
        "relation_identity": "str",
        "source_ref_json": "json",
        "content_hash": "str",
        "occurred_at": "datetime",
        "relative_path": "str",
        "media_type": "str",
        "payload_json": "json",
    },
    "batch_runs": {
        "id": "int",
        "run_id": "str",
        "batch_id": "int",
        "status": "enum",
        "total_case_count": "int",
        "analysis_succeeded_count": "int",
        "error_count": "int",
        "started_at": "datetime",
        "finished_at": "datetime",
        "updated_at": "datetime",
    },
    "case_runs": {
        "id": "int",
        "run_id": "str",
        "case_id": "int",
        "batch_run_id": "int",
        "previous_case_run_id": "int",
        "trigger_type": "enum",
        "status": "enum",
        "current_stage": "str",
        "error_code": "str",
        "error_stage": "str",
        "error_detail_json": "json",
        "started_at": "datetime",
        "finished_at": "datetime",
        "created_at": "datetime",
        "updated_at": "datetime",
    },
    "stage_results": {
        "id": "int",
        "case_run_id": "int",
        "stage_name": "str",
        "contract_version": "str",
        "result_json": "json",
        "result_sha256": "str",
        "created_at": "datetime",
    },
    "model_calls": {
        "id": "int",
        "call_id": "str",
        "case_run_id": "int",
        "stage_name": "str",
        "attempt_no": "int",
        "model_name": "str",
        "prompt_version": "str",
        "request_manifest_json": "json",
        "status": "str",
        "response_json": "json",
        "error_json": "json",
        "started_at": "datetime",
        "finished_at": "datetime",
        "latency_ms": "int",
        "prompt_token_count": "int",
        "completion_token_count": "int",
        "total_token_count": "int",
    },
    "reviews": {
        "id": "int",
        "review_id": "str",
        "submission_id": "str",
        "case_id": "int",
        "case_run_id": "int",
        "outcome": "enum",
        "final_intervention_level": "enum",
        "final_cause_json": "json",
        "final_actions_json": "json",
        "review_reason": "text",
        "execution_note": "text",
        "created_at": "datetime",
    },
}

# 规格 11.1：可空列（其余列 NOT NULL）。
EXPECTED_NULLABLE: dict[str, set[str]] = {
    "data_versions": set(),
    "batches": {"current_batch_run_id"},
    "cases": {
        "system_intervention_level",
        "final_intervention_level",
        "current_case_run_id",
        "current_review_id",
    },
    "evidence": {"occurred_at"},
    "batch_runs": {"finished_at"},
    "case_runs": {
        "batch_run_id",
        "previous_case_run_id",
        "current_stage",
        "error_code",
        "error_stage",
        "error_detail_json",
        "finished_at",
    },
    "stage_results": set(),
    "model_calls": {
        "response_json",
        "error_json",
        "finished_at",
        "latency_ms",
        "prompt_token_count",
        "completion_token_count",
        "total_token_count",
    },
    "reviews": {
        "final_intervention_level",
        "final_cause_json",
        "final_actions_json",
        "review_reason",
        "execution_note",
    },
}

# 规格 11.1 唯一性：全局唯一 / 批次内 / 案例内 / 阶段结果 / 每案例一份 review。
EXPECTED_UNIQUE: dict[str, set[frozenset[str]]] = {
    "data_versions": {frozenset({"data_version"})},
    "batches": {frozenset({"batch_id"})},
    "cases": {frozenset({"batch_id", "case_id"})},
    "evidence": {frozenset({"case_id", "evidence_id"})},
    "batch_runs": {frozenset({"run_id"})},
    "case_runs": {frozenset({"run_id"})},
    "stage_results": {frozenset({"case_run_id", "stage_name"})},
    "model_calls": {frozenset({"call_id"})},
    "reviews": {
        frozenset({"review_id"}),
        frozenset({"submission_id"}),
        frozenset({"case_id"}),
    },
}

# 规格 11.1：外键（表 -> 列 -> 目标表）。
EXPECTED_FKS: dict[str, dict[str, str]] = {
    "data_versions": {},
    "batches": {
        "data_version_id": "data_versions",
        "current_batch_run_id": "batch_runs",
    },
    "cases": {
        "batch_id": "batches",
        "current_case_run_id": "case_runs",
        "current_review_id": "reviews",
    },
    "evidence": {"case_id": "cases"},
    "batch_runs": {"batch_id": "batches"},
    "case_runs": {
        "case_id": "cases",
        "batch_run_id": "batch_runs",
        "previous_case_run_id": "case_runs",
    },
    "stage_results": {"case_run_id": "case_runs"},
    "model_calls": {"case_run_id": "case_runs"},
    "reviews": {"case_id": "cases", "case_run_id": "case_runs"},
}

# ADR-0036：枚举列（函数名冻结值，Python 枚举 + 数据库 CHECK 共同约束）。
EXPECTED_ENUM_VALUES: dict[str, dict[str, set[str]]] = {
    "batches": {
        "status": {
            "PENDING_ANALYSIS",
            "ANALYZING",
            "COMPLETED",
            "COMPLETED_WITH_ERRORS",
        },
    },
    "cases": {
        "status": {
            "PENDING_ANALYSIS",
            "ANALYZING",
            "PENDING_REVIEW",
            "COMPLETED",
            "PROCESSING_ERROR",
        },
        "system_intervention_level": {
            "MUST_INTERVENE",
            "SHOULD_INTERVENE",
            "NO_IMMEDIATE_INTERVENTION",
        },
        "final_intervention_level": {
            "MUST_INTERVENE",
            "SHOULD_INTERVENE",
            "NO_IMMEDIATE_INTERVENTION",
        },
    },
    "batch_runs": {
        "status": {
            "STARTING",
            "RUNNING",
            "COMPLETED",
            "COMPLETED_WITH_ERRORS",
            "FAILED",
            "INTERRUPTED",
        },
    },
    "case_runs": {
        "trigger_type": {"BATCH", "MANUAL_RERUN"},
        "status": {
            "STARTING",
            "PERCEPTION_RUNNING",
            "ATTRIBUTION_RUNNING",
            "STRATEGY_RUNNING",
            "SUCCEEDED",
            "FAILED",
            "INTERRUPTED",
        },
    },
    "reviews": {
        "outcome": {
            "APPROVED",
            "MODIFIED_AND_APPROVED",
            "REJECTED_WITH_JUDGMENT",
            "INSUFFICIENT_EVIDENCE",
        },
        "final_intervention_level": {
            "MUST_INTERVENE",
            "SHOULD_INTERVENE",
            "NO_IMMEDIATE_INTERVENTION",
        },
    },
}

# 规格 10.1/10.3：部分唯一索引（全系统最多一个活动 batch_run；同案例最多一个活动 case_run）。
EXPECTED_PARTIAL_UNIQUE_INDEXES = {
    "batch_runs": ("uq_batch_runs_one_active", {"STARTING", "RUNNING"}),
    "case_runs": (
        "uq_case_runs_one_active_per_case",
        {"STARTING", "PERCEPTION_RUNNING", "ATTRIBUTION_RUNNING", "STRATEGY_RUNNING"},
    ),
}


def _type_family(column: Column[Any]) -> str:
    if isinstance(column.type, Integer):
        return "int"
    if isinstance(column.type, Boolean):
        return "bool"
    if isinstance(column.type, DateTime):
        return "datetime"
    if isinstance(column.type, JSON):
        return "json"
    if isinstance(column.type, SAEnum):
        return "enum"
    if isinstance(column.type, Text):  # Text 是 String 的子类，必须先判断
        return "text"
    if isinstance(column.type, String):
        return "str"
    raise AssertionError(f"未知列类型：{column.type!r}")


def _unique_column_sets(table) -> set[frozenset[str]]:
    result: set[frozenset[str]] = set()
    for constraint in table.constraints:
        if isinstance(constraint, UniqueConstraint):
            result.add(frozenset(column.name for column in constraint.columns))
    for column in table.columns:
        if column.unique:
            result.add(frozenset({column.name}))
    return result


def _fk_map(table) -> dict[str, str]:
    result: dict[str, str] = {}
    for constraint in table.constraints:
        if isinstance(constraint, ForeignKeyConstraint):
            for column, ref in zip(constraint.columns, constraint.elements, strict=True):
                result[column.name] = ref.column.table.name
    return result


def test_exactly_nine_business_tables() -> None:
    assert set(Base.metadata.tables) == NINE_TABLES


def test_column_names_and_type_families_frozen() -> None:
    for table_name, expected in EXPECTED_TYPES.items():
        table = Base.metadata.tables[table_name]
        assert {column.name for column in table.columns} == set(expected), table_name
        for column in table.columns:
            assert _type_family(column) == expected[column.name], (
                f"{table_name}.{column.name} 类型族应为 {expected[column.name]}"
            )


def test_nullability_frozen() -> None:
    for table_name, expected in EXPECTED_NULLABLE.items():
        table = Base.metadata.tables[table_name]
        actual = {column.name for column in table.columns if column.nullable}
        assert actual == expected, table_name


def test_each_table_has_single_integer_pk_named_id() -> None:
    for table_name in NINE_TABLES:
        table = Base.metadata.tables[table_name]
        pks = [
            constraint
            for constraint in table.constraints
            if isinstance(constraint, PrimaryKeyConstraint)
        ]
        assert len(pks) == 1, table_name
        assert [column.name for column in pks[0].columns] == ["id"], table_name
        assert isinstance(table.columns["id"].type, Integer), table_name


def test_unique_constraints_frozen() -> None:
    for table_name, expected in EXPECTED_UNIQUE.items():
        assert _unique_column_sets(Base.metadata.tables[table_name]) == expected, table_name


def test_foreign_keys_frozen() -> None:
    for table_name, expected in EXPECTED_FKS.items():
        assert _fk_map(Base.metadata.tables[table_name]) == expected, table_name


def test_enum_columns_frozen_with_values() -> None:
    for table_name, columns in EXPECTED_ENUM_VALUES.items():
        table = Base.metadata.tables[table_name]
        for column_name, expected_values in columns.items():
            column = table.columns[column_name]
            assert isinstance(column.type, SAEnum), f"{table_name}.{column_name} 不是枚举"
            assert column.type.name == f"{table_name}_{column_name}", (
                f"{table_name}.{column_name} 约束名应冻结为 {table_name}_{column_name}"
            )
            assert set(column.type.enums) == expected_values, (
                f"{table_name}.{column_name} 取值"
            )


def test_local_enums_frozen_values() -> None:
    assert {member.value for member in InterventionLevel} == {
        "MUST_INTERVENE",
        "SHOULD_INTERVENE",
        "NO_IMMEDIATE_INTERVENTION",
    }
    assert {member.value for member in ReviewOutcome} == {
        "APPROVED",
        "MODIFIED_AND_APPROVED",
        "REJECTED_WITH_JUDGMENT",
        "INSUFFICIENT_EVIDENCE",
    }


def test_partial_unique_indexes_declared() -> None:
    for table_name, (index_name, active_statuses) in EXPECTED_PARTIAL_UNIQUE_INDEXES.items():
        table = Base.metadata.tables[table_name]
        index = next(index for index in table.indexes if index.name == index_name)
        assert index.unique, index_name
        where = index.dialect_options["sqlite"]["where"]
        assert where is not None, index_name
        for status in active_statuses:
            assert repr(status) in str(where), index_name
