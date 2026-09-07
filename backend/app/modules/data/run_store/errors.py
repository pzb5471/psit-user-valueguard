"""M1-07：RunStore 错误合同（技术实施规格 8/10.2—10.5/11.2 子集）。

RunStore 命令的可预期失败以 RunStoreError 子类抛出，字段对齐规格 12.4：

- code：稳定错误编号（RESOURCE_NOT_FOUND / ACTIVE_RUN_CONFLICT /
  RUN_NOT_ACTIVE / INCOMPLETE_DECISION_PACKAGE / STAGE_RESULT_CONFLICT）；
- message：中文可操作说明；
- object_type/object_id：对象类型与公开标识（batch/case/case_run/run_id）；
- next_action：中文下一步动作。

写入类命令在单个短事务内执行（规格 8/11.2）：任何校验失败整体回滚，不允许
留下半写入状态；数据库层活动唯一约束（SQLite 部分唯一索引）是最终保护
（规格 10.1），违反时统一转 ACTIVE_RUN_CONFLICT。
"""

from __future__ import annotations


class RunStoreError(Exception):
    """RunStore 可预期失败基类（字段对齐规格 12.4）。"""

    def __init__(
        self,
        *,
        code: str,
        message: str,
        object_type: str = "run",
        object_id: str = "",
        stage: str = "run_store",
        next_action: str = "检查运行状态后重试",
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.object_type = object_type
        self.object_id = object_id
        self.stage = stage
        self.next_action = next_action


class RunStoreResourceNotFoundError(RunStoreError):
    """批次/案例/运行不存在：命令按公开标识定位失败（M3 映射 404）。"""

    def __init__(self, *, object_type: str = "run", object_id: str = "") -> None:
        super().__init__(
            code="RESOURCE_NOT_FOUND",
            message="运行记录不存在",
            object_type=object_type,
            object_id=object_id,
            stage="run_store",
            next_action="检查 batch_id/case_id/run_id 后重试",
        )


class ActiveRunConflictError(RunStoreError):
    """同一案例或全系统已存在活动运行（规格 10.1：数据库约束最终保护）。"""

    def __init__(self, *, object_type: str, object_id: str = "") -> None:
        target = "批次" if object_type == "batch" else "案例"
        super().__init__(
            code="ACTIVE_RUN_CONFLICT",
            message=f"{target}已存在进行中的分析运行",
            object_type=object_type,
            object_id=object_id,
            stage="run_store",
            next_action="等待当前运行结束，或确认无残留活动运行后重试",
        )


class RunNotActiveError(RunStoreError):
    """命令目标运行已结束（SUCCEEDED/FAILED/INTERRUPTED），禁止再写入或发布。"""

    def __init__(self, *, object_id: str = "") -> None:
        super().__init__(
            code="RUN_NOT_ACTIVE",
            message="运行已结束，不能继续追加事件或发布结果",
            object_type="case_run",
            object_id=object_id,
            stage="run_store",
            next_action="确认运行状态后重新发起分析",
        )


class IncompleteDecisionPackageError(RunStoreError):
    """完整发布前缺少阶段结果（规格 10.4：不发布半个决策包）。"""

    def __init__(self, *, object_id: str = "", missing_stages: tuple[str, ...] = ()) -> None:
        detail = "、".join(missing_stages) if missing_stages else "未知阶段"
        super().__init__(
            code="INCOMPLETE_DECISION_PACKAGE",
            message=f"完整决策包缺少阶段结果：{detail}",
            object_type="case_run",
            object_id=object_id,
            stage="run_store",
            next_action="补齐全部阶段结果后重新发布",
        )


class StageResultConflictError(RunStoreError):
    """同一 case_run+stage_name 已存在内容不同的阶段结果（只追加不覆盖：规格 11.2）。"""

    def __init__(self, *, object_id: str = "", stage_name: str = "") -> None:
        super().__init__(
            code="STAGE_RESULT_CONFLICT",
            message=f"阶段结果已存在且内容不同：{stage_name}",
            object_type="case_run",
            object_id=object_id,
            stage="run_store",
            next_action="确认阶段结果来源后重试",
        )


__all__ = [
    "ActiveRunConflictError",
    "IncompleteDecisionPackageError",
    "RunNotActiveError",
    "RunStoreError",
    "RunStoreResourceNotFoundError",
    "StageResultConflictError",
]
