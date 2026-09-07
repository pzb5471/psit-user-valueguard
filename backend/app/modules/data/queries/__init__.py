"""M1-05：CaseQueryGateway 查询投影包（技术实施规格 8/10.3/12.1/12.2）。

对外只暴露查询网关；业务投影 DTO 白名单与冻结枚举见 views.py（规格 12.2），
只读仓储见 repositories.case_query_repository。
"""

from .gateway import CaseQueryGateway

__all__ = ["CaseQueryGateway"]
