# M2-10 真实 GLM 验收

本目录只运行真实 `GlmClient`，不使用 `ScriptedGlmClient`，也不进入普通 PR 门禁。

1. 运行 `scripts/prepare-demo-data.ps1`，生成固定 10 个 DEMO 与 5 个 ACCEPTANCE 案例。
2. 只通过环境变量配置 `ZAI_API_KEY`。
3. 运行 `scripts/test.ps1 -Task M2-10`。测试会继续跑完全部案例，并把模型尝试、阶段结果、Token、耗时和失败记录写入 `artifacts/poc/<run_id>/`。
4. 演讲版 MVP 按 ADR 0087 使用项目负责人基于多轮真实运行记录的演示验收，不再重复执行双人复核。
5. 自动结构门通过后，在受审查提交中启用 `config/default.toml` 的 `analysis.production_enabled`；缺少 Key 时仍安全关闭分析。

可分别设置 `PSIT_POC_REASONING_EFFORT=high|max` 与 `PSIT_POC_CONCURRENCY=1|2|3` 重跑并比较产物。密钥、运行 ZIP 和密封参考均不得进入 Git。

## 2026-09-11 参数结论

- 正式参数选择 `reasoning_effort=high`、案例并发 `2`、`max_tokens=4096`、完整响应上限 `300` 秒。
- 最终自动结构门 run_id 为 `20260911T040909Z`：15/15 案例、45/45 阶段通过，无失败模型尝试。
- `max + 并发 2` 的对照 run_id `20260911T033245Z` 仅 2/15 案例成功，13 次请求没有返回可校验正文，因此不得用于正式运行。
- 并发 1 全部通过但总耗时明显更长；并发 3 全部通过但出现一次可恢复连接错误且需要更多定向修复。并发 2 在速度和稳定性之间更合适。
- 项目负责人演示验收已按 ADR 0087 确认，生产开关可以在本次受审查提交中启用。
