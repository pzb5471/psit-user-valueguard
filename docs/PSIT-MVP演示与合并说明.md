# PSIT MVP 演示与合并说明

## 当前结论

代码、仓库自带固定演示包、真实 GLM 自动结构门、项目负责人多轮演示验收和确定性产品闭环已经通过。生产分析默认启用；运行时提供 `ZAI_API_KEY` 后使用真实 GLM-5.3-Flash，缺少 Key 时只关闭分析能力，不影响工作台读取历史结果。

## 2026-09-11 正式复验证据

- 在全新隔离运行目录中，从仓库内 `mvp/mvp_batch_v1.zip` 导入 10 个案例和 164 条证据，HTTP 分别返回导入 `201`、开始分析 `202`。
- 批次运行 `BR-3037dcc286ae4ce68eb47ac3ca963422` 于 13:22:33—13:26:38 完成：10/10 案例成功、0 错误、30/30 阶段结果持久化。
- SQLite 保存 30 条互不重复的真实模型调用明细：感知、归因、策略各 10 条；无重试、无 429；总计 164,832 Token。该数值是本次固定演示运行记录，不是以后运行的费用承诺。
- 浏览器实际完成批次队列、案例详情、真实结论、图片证据展开和“直接通过”；刷新后结果只读。停止并重新启动正式服务后，批次、案例、审核结果和模型调用记录均完整读回。
- 复验中修复了并发案例模型调用编号冲突：调用编号现在包含案例运行 ID，避免不同案例同阶段记录被误判为重复；回归测试固定了跨运行唯一、同运行幂等的边界。

## 合并边界

1. ADR 0087 记录项目负责人已经基于多轮真实运行完成演讲版验收，不再重复执行双人复核。
2. 固定 15 案例、45 阶段自动 PoC、完整测试和正式网页演示仍必须保留可复算证据。
3. 双人复核表只作为未来业务试点的可选模板，不阻塞 PR、生产开关或演讲。
4. 本分支只通过 PR #29 合入 `main`，本机不直接向 `main` 提交或推送。

API Key 由演示者自行管理，只在启动时临时输入；仓库、配置、日志、页面和数据库均不保存密钥。

## 正式演示准备

在仓库根目录运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-with-key.ps1
```

浏览器打开 `http://127.0.0.1:8000`。启动窗口不要关闭；演示结束在该窗口按 `Ctrl+C`，让 SQLite、后台任务和实例锁按规则释放。

演示主路径采用“提前真实跑好并保存结果”：

1. 导入仓库内的 `mvp/mvp_batch_v1.zip`，说明页面显示的是模拟数据环境，导入不会自动调用模型。
2. 明确点击开始分析，展示进度与案例队列。
3. 打开一个带图片的完成案例，依次说明高价值结论、风险原因、证据、图片观察、不确定性和建议动作。
4. 展示一次直接通过、一次修改后确认、一次证据不足或驳回。
5. 刷新页面或直接重新打开案例地址，证明结果来自 SQLite 持久化，不依赖浏览器内存。
6. 正式演讲前提前完成一次真实分析并保留 SQLite 结果；现场可以重新运行一个案例，网络异常时展示已保存的真实结果，不把确定性测试替身冒充真实模型。

## 演示前技术检查

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\bootstrap.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test.ps1 -Task M1-09
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test.ps1 -Task M4-09
```

启动失败时先检查 8000 端口、`runtime_data/psit.lock` 的持有进程、前端构建和配置文件；不得用删除数据库或结束未知进程规避问题。

## GitHub 合并方式

本项目继续遵守 `main` 只 pull、不 push。所有修复先推送 `task/RUN-01-mvp-runtime-fixes`，通过 Pull Request #29 合并到 `main`；不要在本机把任务分支直接合进 `main`。完整门禁和正式生产演示已经通过，PR 可转为 Ready for review，再由项目负责人在 GitHub 上完成合并。
