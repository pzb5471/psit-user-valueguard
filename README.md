# PSIT 高价值客户异常售后决策支持 MVP

这是一个可在单台 Windows 电脑上运行和演示的本地 Web MVP。它导入脱敏模拟案例，调用 GLM-5.3-Flash 完成感知、归因和策略三个阶段，将结果与人工确认持久化到 SQLite，并通过 React 工作台展示完整证据链。

## 快速开始

首次使用先安装冻结依赖：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\bootstrap.ps1
```

正式演示时安全输入 ZAI API Key 并启动：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-with-key.ps1
```

打开 `http://127.0.0.1:8000`，导入仓库内的 `demo/demo_batch_v1.zip`，再点击“开始分析”。API Key 只存在于当前启动进程，不写入仓库、配置、页面或数据库。演示结束后在启动窗口按 `Ctrl+C` 正常关闭。

## 验证

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test.ps1 -Task M1-09
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test.ps1 -Task M4-09
```

完整演示顺序、已验证证据和故障处理见 [PSIT MVP 演示与合并说明](docs/PSIT-MVP演示与合并说明.md)，技术合同见 [PSIT MVP 技术实施规格](docs/PSIT-MVP技术实施规格.md)。

## 证据边界

仓库内案例均为脱敏 Mock 数据。本项目证明固定案例的核心产品链路可以运行，不证明真实业务准确率、客户留存提升、ROI 或企业生产可用性，也不会执行真实退款、补偿或联系客户。
