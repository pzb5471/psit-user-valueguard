# 将批次运行和案例运行拆成两张表

原设计中的单一 `runs` 无法同时清楚表达“一次批次启动”和“一个案例的一次分析或重新分析”。两者拆为 `batch_runs`、`case_runs`，SQLite 核心表由八张调整为九张：`data_versions`、`batches`、`cases`、`evidence`、`batch_runs`、`case_runs`、`stage_results`、`model_calls`、`reviews`。

`data_versions` 一对多关联 `batches`；`batches` 一对多关联 `cases` 和 `batch_runs`；`cases` 一对多关联 `evidence`、`case_runs` 和 `reviews`；首次批量分析的 `case_run` 关联对应 `batch_run`，人工单案例重跑不关联原批次运行，而是通过 `previous_case_run_id` 连接上一个案例运行；`case_runs` 一对多关联 `stage_results`、`model_calls` 和 `reviews`。每条 `review` 同时关联案例和被审核的案例运行，数据库约束保证二者归属一致。

一次批量开始创建一条 `batch_run` 和每案例一条 `case_run`；这些首次案例运行的 `batch_run_id` 必填，`trigger_type` 为 `BATCH`。单案例重新分析只新增 `case_run`，其 `batch_run_id` 为空、`trigger_type` 为 `MANUAL_RERUN`，并指向上一个案例运行，不创建假的整批运行，也不回写原批次统计。拆表增加一个模型和一次迁移，但消除了范围类型分支和批次进度与案例版本混用的问题。
