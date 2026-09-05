# 保持跨模块合同纯净且严格

四个模块需要共享案例、分析和状态含义，但共享目录若导入 FastAPI、SQLAlchemy、SDK 或业务实现，会迅速变成第五个耦合模块。宽松模型又会在模块边界静默接受错误类型。

`backend/app/contracts/` 只保存 `data.py`、`analysis.py` 和 `states.py` 三类纯合同，只依赖标准库、`typing` 与 Pydantic。Pydantic 使用严格校验并禁止额外字段，行为接口使用 Python `Protocol`。现有 `CaseInput v1` 和三阶段结果继续作为字段真源，不新造无数据来源字段。

业务 API DTO 仍由 M3 维护并生成 OpenAPI。共享合同不得导入模块，模块不得复制一份合同自行修改，也不引入通用企业框架。
