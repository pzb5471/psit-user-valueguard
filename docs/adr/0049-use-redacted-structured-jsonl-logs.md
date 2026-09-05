# 使用脱敏结构化 JSONL 日志贯通一次运行

应用技术日志统一写入 `runtime_data/logs/app.jsonl`，采用稳定 JSONL 字段：`timestamp`、`level`、`trace_id`、`batch_id`、`case_id`、`run_id`、`stage`、`event`、`status`、`duration_ms`、`error_code`。同一次请求经过 API、`RunService`、Agent、`GlmClient` 和数据库写入时沿用同一 `trace_id`。

单个日志文件达到 10 MB 后轮换，保留最近 5 个备份。日志不记录 API Key、图片 base64、完整客户对话、完整 Prompt、本机绝对路径或密封验收答案；Prompt 只记录版本和 SHA-256。供应商原始响应保存在 `model_calls`，不重复写入日志。

技术日志只供开发排障，不建立业务日志页，也不通过业务 DTO 返回。业务错误继续使用稳定错误编号、中文摘要和可执行下一步。
