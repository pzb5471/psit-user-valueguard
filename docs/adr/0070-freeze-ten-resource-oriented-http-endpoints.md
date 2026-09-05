# 冻结十个面向产品动作的 HTTP 接口

三个页面只需要导入、批次、运行、队列、详情、重跑、审核、证据和健康检查。增加通用 CRUD、技术查询或多种响应外壳会扩大 M3、M4 的并行合同面。

`/api/v1` 固定十个接口。单项直接返回业务资源，列表返回 `items` 和 `total`，写操作返回接受或保存后的 `BatchWorkspaceView`、`CaseDetailView` 或 `ReviewResultView`；健康检查使用独立 `HealthView`。开始和重跑使用 `202`，不等待 GLM。

不增加运行详情、阶段结果、模型调用、通用搜索、删除、配置和日志接口。业务响应不使用只有 `success: true` 的空外壳。
