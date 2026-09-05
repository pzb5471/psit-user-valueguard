# 使用明确的业务响应 DTO

FastAPI 为工作台建立 `BatchWorkspaceView`、`CaseQueueItemView`、`CaseDetailView`、`ReviewResultView` 和 `BusinessError` 五类 Pydantic 响应 DTO。每个业务接口显式声明 `response_model`，由服务层从数据库记录、当前有效运行和人工结果组装 DTO；不得直接序列化 SQLAlchemy 对象，也不得先返回全部字段再依靠 React 隐藏。

批次、案例和证据文本标识只为路由、关联和必要错误定位返回。数据库整数主键、数据版本、Schema、内部运行编号、阶段结果、模型调用、Prompt、Token、供应商响应、技术日志和原始 JSON 不属于业务 DTO。`stage_results`、`model_calls` 不提供业务查询接口，开发测试通过数据库和内部日志核验。

这层映射会增加少量代码，但能让数据库为了追溯继续保存完整信息，同时从服务端保证业务页面只收到明确允许的结果。
