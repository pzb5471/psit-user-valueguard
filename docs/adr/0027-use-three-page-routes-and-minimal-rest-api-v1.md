# 使用三层页面路由和最小 REST API v1

React 工作台只保留三个页面地址：`/` 是入口，没有批次时显示 ZIP 导入，有批次时进入最近批次；`/batches/:batchId` 显示批次摘要、运行进度和案例队列；`/batches/:batchId/cases/:caseId` 显示案例详情、证据和人工确认。用户刷新详情或使用浏览器返回时，页面根据地址中的标识从后端恢复状态，React 内存不作为业务真源。

FastAPI 接口统一以 `/api/v1` 开头，只提供以下十项能力：

1. `POST /api/v1/batches`：上传并导入标准案例 ZIP。
2. `GET /api/v1/batches`：查询历史批次。
3. `GET /api/v1/batches/{batch_id}`：查询批次摘要和进度。
4. `POST /api/v1/batches/{batch_id}/runs`：明确启动批量分析。
5. `GET /api/v1/batches/{batch_id}/cases`：查询所选批次案例队列。
6. `GET /api/v1/batches/{batch_id}/cases/{case_id}`：查询案例详情。
7. `POST /api/v1/batches/{batch_id}/cases/{case_id}/reruns`：重新分析允许重跑的案例。
8. `POST /api/v1/batches/{batch_id}/cases/{case_id}/reviews`：提交人工最终确认。
9. `GET /api/v1/batches/{batch_id}/cases/{case_id}/evidence/{evidence_id}/content`：读取证据图片。
10. `GET /api/v1/health`：检查应用是否正常启动。

开始批量分析返回更新后的批次业务视图，案例重跑返回更新后的案例业务视图；前端按 `batch_id` 和 `case_id` 轮询，不接收批次运行或案例运行编号。v1 不建设 GraphQL、登录、模型配置、技术日志、通用搜索、永久删除和独立数据管理接口。这组边界牺牲了通用性，但让每个前端动作、后端职责和测试任务都能一一对应。
