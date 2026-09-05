# 只暴露最小业务 DTO 和运行健康视图

页面只需要批次摘要、案例队列、案例详情和人工结果。若先把数据库或 Agent 结构全部返回再由 React 隐藏，内部字段会进入 OpenAPI、网络响应和前端缓存。

`BatchWorkspaceView`、`CaseQueueItemView`、`CaseDetailView` 和 `ReviewResultView` 只保存页面完成动作所需的业务字段，按需省略不适用内容；`BusinessError` 统一错误。`HealthView` 只表达应用、数据库和分析能力状态，是运行视图，不属于分析结果 DTO。

DTO 不返回 RFM 方法、数据与 Schema 版本、运行编号、数据库主键、Prompt、Token、模型记录、路径、哈希、来源 JSON 或技术日志。
