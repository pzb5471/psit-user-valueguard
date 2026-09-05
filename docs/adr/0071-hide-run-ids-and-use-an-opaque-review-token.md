# 隐藏运行编号并使用不可读审核 Token

已有规则一方面要求开始分析返回运行标识，另一方面禁止业务 API 暴露运行编号；人工审核又必须确认页面看到的结果仍是当前结果。这三项需要统一。

开始分析返回 `202 BatchWorkspaceView`，重跑返回 `202 CaseDetailView`，前端只按批次和案例地址轮询，不返回 `batch_run_id` 或 `case_run_id`。允许审核时，案例详情提供不展示的 `review_token`；当前结果变化后 Token 改变，旧 Token 返回 `409 STALE_CASE_RESULT`。M1 在保存事务中仍校验并关联内部真实 `case_run_id`。

Token 只用于并发一致性，不是运行编号、认证或授权凭证。业务页面不显示 Token，也不允许用户编辑。
