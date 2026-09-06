"""M1-07：RunStore（技术实施规格 8/9.2/10.1—10.5/11.1—11.2）。

对外只暴露 RunStore 短事务命令与 DTO；错误合同见 errors.py，写仓储见
repository.py。批次/案例当前投影由查询网关只读（规格 10.3），本网关只写
运行历史、阶段事件追加与完整决策包原子发布；HTTP 接口由 M3 提供。
"""

from .errors import (
    ActiveRunConflictError,
    IncompleteDecisionPackageError,
    RunNotActiveError,
    RunStoreError,
    RunStoreResourceNotFoundError,
    StageResultConflictError,
)
from .gateway import (
    APP_INTERRUPTED_CODE,
    APP_RECOVERY_STAGE,
    COMPLETE_PACKAGE_STAGES,
    RunStore,
)
from .types import (
    BatchRunView,
    CaseRunView,
    FailureResult,
    ModelAttemptInput,
    PublishResult,
    RecoverySummary,
    StageResultInput,
)

__all__ = [
    "APP_INTERRUPTED_CODE",
    "APP_RECOVERY_STAGE",
    "COMPLETE_PACKAGE_STAGES",
    "ActiveRunConflictError",
    "BatchRunView",
    "CaseRunView",
    "FailureResult",
    "IncompleteDecisionPackageError",
    "ModelAttemptInput",
    "PublishResult",
    "RecoverySummary",
    "RunNotActiveError",
    "RunStore",
    "RunStoreError",
    "RunStoreResourceNotFoundError",
    "StageResultConflictError",
    "StageResultInput",
]
