# 人工单案例重跑不计入原批次进度

批量开始时创建一条 `batch_run`，并为每个案例创建一条 `case_run`。这些首次案例运行的 `batch_run_id` 必填，`trigger_type` 为 `BATCH`。批次的总数、分析成功数和异常数只统计直接属于该 `batch_run` 的首次案例运行。

人工重新分析单个案例时只创建新 `case_run`：`batch_run_id` 为空，`trigger_type` 为 `MANUAL_RERUN`，`previous_case_run_id` 指向当时的当前案例运行。重跑完成后原子切换 `cases.current_case_run_id`，但不回写已经结束的批次统计，也不创建没有业务意义的单案例批次运行。

这意味着 `case_runs.batch_run_id` 是有明确条件的可空外键，而不是含义不清的空字段。它能区分“本次批次第一次处理了多少案例”和“某个案例后来被重试了多少次”。
