# 锁定 Python、Node 和项目级执行入口

团队并行开发必须在不同成员机器上得到同一依赖图和同一执行入口。后端统一使用 Python 3.12、`pyproject.toml`、`uv` 和 `uv.lock`；前端统一使用 Node.js 24、pnpm 11、`package.json` 和 `pnpm-lock.yaml`。精确依赖版本在仓库初始化和兼容性验证后写入锁文件，不在技术讨论阶段凭经验猜测。

仓库提供 `scripts/bootstrap.ps1`、`scripts/dev.ps1`、`scripts/test.ps1`、`scripts/start.ps1`，分别承担初始化、开发启动、完整测试和演示启动。脚本检查解释器、包管理器主版本和锁文件一致性，失败时停止并给出明确修复信息。

脚本只允许使用项目相对路径、PATH 或项目级工具发现逻辑，不依赖 WindowsApps 的 Python 别名，不写任何成员电脑目录或 Codex 缓存绝对路径。
