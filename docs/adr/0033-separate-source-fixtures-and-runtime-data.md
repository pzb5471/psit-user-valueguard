# 分离源码、测试夹具和本机运行数据

仓库按 `backend/`、`frontend/`、`schemas/`、`prompts/`、`policies/`、`migrations/`、`scripts/` 和 `tests/` 组织。前端构建结果位于不手工维护的 `frontend/dist/`，只有输入内容指纹和静态文件清单与当前代码一致时才由 FastAPI 提供，否则演示启动器先重建并在失败时停止。固定运行包放入 `tests/fixtures/runtime/`；密封人工参考答案放入 `tests/fixtures/evaluation/`，不得复制到产品运行目录或发送给运行 Agent。

后端固定使用 Python 3.12、`pyproject.toml`、uv 和 `uv.lock`；前端固定使用 Node.js 24、pnpm 11、`package.json` 和 `pnpm-lock.yaml`。项目不依赖 Codex 缓存路径、Windows 应用商店 Python 别名或某个成员电脑的绝对路径。`scripts/bootstrap.ps1` 负责环境检查和依赖同步，`scripts/dev.ps1` 启动开发环境，`scripts/test.ps1` 运行检查，`scripts/start.ps1` 验证或重建前端、按需备份并迁移数据库后启动本机产品，`scripts/stop.ps1` 请求同一安全关闭流程。

本机状态默认放入项目根目录下、不提交 Git 的 `runtime_data/`，并允许不入 Git 的本机配置显式改到另一处本地根目录：数据库为 `psit.db`，临时导入为 `imports/tmp/`，正式批次为 `batches/<batch_id>/<data_version>/`，技术日志和数据库备份分别为 `logs/`、`backups/`。SQLite 只保存相对已解析根目录的文件路径和校验值，不保存图片 BLOB。

统一启动脚本先检查配置和目录权限并取得系统独占锁；检测到已有数据库且 revision 落后时，先用 SQLite backup API 生成通过完整性检查的备份，再执行 Alembic 升级，最后启动默认监听 `127.0.0.1:8000` 的 FastAPI。没有迁移时不自动生成重复备份；迁移失败立即停止，不删除、不自动重建数据库。空数据库允许由 Alembic 正常创建。
