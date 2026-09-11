# PSIT MVP 演示与合并说明

## 当前结论

代码、固定案例、真实 GLM 自动结构门和确定性产品闭环已经通过。生产分析开关仍为关闭状态，因为项目规定的两名业务验收者复核尚未完成；在该人工门完成以前，本分支可以评审，但不应合入 `main` 后对外宣称“正式 MVP 全部验收完成”。

## 合并前只剩的业务动作

1. 用户与一名队友分别填写 `docs/poc/GLM-5.3-Flash双人复核表.md`，逐案检查 5 个验收案例。
2. 两人全部通过后，把 `config/default.toml` 中的 `analysis.production_enabled` 改为 `true`。
3. 使用新的本机环境变量密钥重跑 M2-10、全量测试、M1-09、M4-09 和生产启动闭环。
4. 把生产开关与最终验收记录追加提交到同一个任务分支，等待 GitHub 检查通过后再合并 PR。

不得把聊天中出现过的密钥继续当作长期密钥。正式演示前应在智谱控制台轮换或撤销旧密钥，只把新密钥配置到演示电脑的临时环境变量。

## 正式演示准备

在仓库根目录运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-with-key.ps1
```

浏览器打开 `http://127.0.0.1:8000`。启动窗口不要关闭；演示结束在该窗口按 `Ctrl+C`，让 SQLite、后台任务和实例锁按规则释放。

演示主路径采用“提前真实跑好并保存结果”：

1. 导入 `demo_batch_v1.zip`，说明页面显示的是模拟数据环境，导入不会自动调用模型。
2. 明确点击开始分析，展示进度与案例队列。
3. 打开一个带图片的完成案例，依次说明高价值结论、风险原因、证据、图片观察、不确定性和建议动作。
4. 展示一次直接通过、一次修改后确认、一次证据不足或驳回。
5. 刷新页面或直接重新打开案例地址，证明结果来自 SQLite 持久化，不依赖浏览器内存。
6. 现场模型调用只作为可选加分项；网络异常时使用提前保存的真实结果，不把确定性测试替身冒充真实模型。

## 演示前技术检查

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\bootstrap.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\prepare-demo-data.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test.ps1 -Task M4-09
```

启动失败时先检查 8000 端口、`runtime_data/psit.lock` 的持有进程、前端构建和配置文件；不得用删除数据库或结束未知进程规避问题。

## GitHub 合并方式

本项目继续遵守 `main` 只 pull、不 push。所有修复先推送 `task/RUN-01-mvp-runtime-fixes`，通过 Pull Request 合并到 `main`；不要在本机把任务分支直接合进 `main`。当前 PR 应保持为待人工门完成的评审状态，双人复核与最终生产验证追加到同一分支后再合并。
