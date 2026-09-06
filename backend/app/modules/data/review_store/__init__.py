"""M1-08：ReviewStore（技术实施规格 8/10.3/11.1/12.3/12.4）。

对外只暴露 ReviewStore 短事务命令与 DTO；错误合同见 errors.py，写仓储见
repository.py。正式人工确认经 reviews 表原子写入并同事务同步案例/批次当前
投影（规格 10.3 同源公式）；业务读取仍走 M1-05 查询网关只读。HTTP 接口由
M3 提供。
"""

from .errors import (
    CaseAlreadyCompletedError,
    ReviewFieldValidationError,
    ReviewStoreError,
    ReviewStoreResourceNotFoundError,
    StaleCaseResultError,
)
from .gateway import ReviewStore
from .types import ReviewSubmitInput

__all__ = [
    "CaseAlreadyCompletedError",
    "ReviewFieldValidationError",
    "ReviewStore",
    "ReviewStoreError",
    "ReviewStoreResourceNotFoundError",
    "ReviewSubmitInput",
    "StaleCaseResultError",
]
