# 冻结九表逻辑 Schema、枚举和时间含义

数据库逻辑字段冻结如下；字符串长度、索引名称和 Python 类名不在本决定中锁死。

| 表 | 独立列 |
|---|---|
| `data_versions` | `id`、`data_version`、`source_snapshot_ref`、`source_manifest_sha256`、`provenance_json`、`created_at` |
| `batches` | `id`、`batch_id`、`data_version_id`、`schema_version`、`package_sha256`、`package_relative_path`、`status`、`case_count`、`analysis_succeeded_count`、`error_count`、`current_batch_run_id`、`imported_at`、`updated_at` |
| `cases` | `id`、`batch_id`、`case_id`、`schema_version`、`case_input_json`、`customer_display_id`、`is_high_value`、`status`、`system_intervention_level`、`final_intervention_level`、`current_case_run_id`、`current_review_id`、`imported_at`、`updated_at` |
| `evidence` | `id`、`case_id`、`evidence_id`、`modality`、`sequence_no`、`identity`、`relation_identity`、`source_ref_json`、`content_hash`、`occurred_at`、`relative_path`、`media_type`、`payload_json` |
| `batch_runs` | `id`、`run_id`、`batch_id`、`status`、`total_case_count`、`analysis_succeeded_count`、`error_count`、`started_at`、`finished_at`、`updated_at` |
| `case_runs` | `id`、`run_id`、`case_id`、`batch_run_id`、`previous_case_run_id`、`trigger_type`、`status`、`current_stage`、`error_code`、`error_stage`、`error_detail_json`、`started_at`、`finished_at`、`created_at`、`updated_at` |
| `stage_results` | `id`、`case_run_id`、`stage_name`、`contract_version`、`result_json`、`result_sha256`、`created_at` |
| `model_calls` | `id`、`call_id`、`case_run_id`、`stage_name`、`attempt_no`、`model_name`、`prompt_version`、`request_manifest_json`、`status`、`response_json`、`error_json`、`started_at`、`finished_at`、`latency_ms`、可选 Token 计数 |
| `reviews` | `id`、`review_id`、`submission_id`、`case_id`、`case_run_id`、`outcome`、`final_intervention_level`、`final_cause_json`、`final_actions_json`、`review_reason`、`created_at` |

同一案例运行每个阶段只保存一份通过合同校验的最终 `stage_result`；修复和重试过程保存在多条 `model_calls`。v1 每个案例最多一份正式人工确认。业务接口不返回 `case_run_id`；提交审核时通过不可读 `review_token` 表明页面所见结果，存储事务再校验内部案例运行仍属于该案例且仍为当前运行，否则返回 `STALE_CASE_RESULT`。

`batches.status`、`analysis_succeeded_count` 和 `error_count` 表示案例当前投影，人工重跑时随当前案例状态原子更新；`batch_runs` 的对应统计只保存首次批量运行历史，人工重跑不得改写。

案例状态固定为 `PENDING_ANALYSIS`、`ANALYZING`、`PENDING_REVIEW`、`COMPLETED`、`PROCESSING_ERROR`。批次业务状态固定为 `PENDING_ANALYSIS`、`ANALYZING`、`COMPLETED`、`COMPLETED_WITH_ERRORS`。案例运行内部状态固定为 `STARTING`、`PERCEPTION_RUNNING`、`ATTRIBUTION_RUNNING`、`STRATEGY_RUNNING`、`SUCCEEDED`、`FAILED`、`INTERRUPTED`。批次运行内部状态固定为 `STARTING`、`RUNNING`、`COMPLETED`、`COMPLETED_WITH_ERRORS`、`FAILED`、`INTERRUPTED`。触发类型、审核结果和介入等级同样使用冻结枚举，并由 Python 枚举和数据库 `CHECK` 共同约束。

批次页面使用“总案例数、分析完成数、处理异常数”。分析完成数只表示已经成功形成决策包的首次案例运行数；人工重跑不改写原批次计数。程序时间统一保存为带毫秒的 UTC ISO 8601，页面转换为北京时间；源中不存在的事件时间不得补造。
