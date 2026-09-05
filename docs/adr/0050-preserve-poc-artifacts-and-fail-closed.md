# 保存可复算 PoC 产物并在失败时关闭通过出口

每次正式 PoC 都生成 `docs/poc/glm-5.3-flash-poc.md`、`artifacts/poc/<run_id>/summary.json` 和 `artifacts/poc/<run_id>/case-results.json`。报告引用对应 `run_id`；汇总保存配置、门槛、耗时和错误统计，逐案例结果保存阶段结果与评分状态，但不包含密封参考答案正文。PoC 验收产物与 `runtime_data/` 分离，不只留在终端输出中。

PoC 失败时固定按输入与证据、Prompt 与 Schema、本地校验器、`reasoning_effort=high/max`、并发 1/2/3 的顺序定位，每次改变后完整重跑固定案例集。禁止改密封答案、删除失败案例、泄漏答案、放宽证据和动作规则、使用预写静态答案或把多个局部成功结果拼成一次通过。

只有全部满足固定门槛后才能冻结正式参数。`high` 与 `max` 都不能通过时，明确判定 GLM-5.3-Flash 当前路线未达到可用 MVP 门槛，并依据失败证据重新决定技术路线。
