# 使用全局唯一的公开批次标识

批次 API 地址只使用 `batch_id`，因此 `batch_id` 在整个系统中全局唯一。完全相同的 ZIP 按 `package_sha256` 返回已有批次；任何已有 `batch_id` 对应不同内容时，无论其 `data_version` 是否相同，都返回 `BATCH_ID_CONFLICT`。数据或映射发生变化时必须生成新的数据版本和新的批次标识。

所有表使用 SQLite 整数主键承担内部关联，业务 API 不暴露这些整数。`data_version`、`batch_id`、`run_id`、`review_id`、`submission_id` 分别全局唯一；`case_id` 在所属批次内唯一，`evidence_id` 在所属案例内唯一。运行、审核和提交标识使用程序生成的 UUID 文本。

把数据版本追加到每条批次 API 地址也可以消除歧义，但会让页面路由、前端状态和所有关联接口同时携带两个标识。当前批次本来就是一次独立导入，直接要求其公开标识全局唯一更简单。
