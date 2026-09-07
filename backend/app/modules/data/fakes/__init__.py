"""M1 数据层测试替身：内存版 ReviewStore（契约测试用，不依赖数据库）。

与 SQLite 真网关同签名/同错误码/同返回类型；真实字段规则复用
review_store.gateway 的模块级纯函数，保证契约不漂移。
"""

from .FakeReviewStore import FakeReviewStore

__all__ = ["FakeReviewStore"]
