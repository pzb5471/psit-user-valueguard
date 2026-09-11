# 跨模块集成不变量

本文记录 M1—M4 合并后已由回归测试固定的集成规则。

- M2 `image_observations` 引用图片时使用 `image_evidence_id`。M1 查询投影必须同时兼容读取旧运行数据中的 `evidence_id`，否则模型已分析的图片会在界面中消失。
- 新增含安装脚本的 pnpm 依赖时，必须在 `pnpm-workspace.yaml` 的 `allowBuilds` 中显式标记允许或禁止，保证冻结锁文件的全新环境安装可重复。
- FastAPI 托管 React 时，只有无扩展名的前端路由可回退到 `index.html`；`/api`、`/e2e` 与缺失的静态资源必须保留原始 404，避免前端兜底遮蔽后端错误。
- 真实 GLM 尚未通过 M2-10 验收时，批次视图必须禁用分析入口，直接调用运行接口必须在产生数据写入前返回 `ANALYSIS_UNAVAILABLE`。
- 真实 API 端到端测试必须覆盖导入、分析、队列、详情、图片证据、人工确认与刷新读回，并断言浏览器过程没有外网请求。
- `ZAI_API_KEY` 存在只表示凭证已提供，不能单独把分析健康状态改成可用；生产装配还必须经过 `analysis.production_enabled` 显式门禁，并实际构造 `GlmClient` 与 `AnalysisEngine`。
- 生产图片解析必须同时受当前 `batch_id`、`data_version`、案例图片清单和 `content_hash` 约束，不能只按一个全局相对路径读取字节。
- 正式 M1-09 验收不得把缺少外部源数据转换为 `skip` 后绿色退出；普通全量回归可以跳过外部依赖，任务验收入口必须把同一缺口报告为失败。
- 生产启动应在创建运行目录、迁移数据库之前预检监听端口；端口冲突统一返回稳定错误码 `PORT_IN_USE`，避免失败启动留下新的本地状态。
- 当策略结果使用 `NO_IMMEDIATE_INTERVENTION` 时，动作只能是 `NO_ACTION_MONITOR`；当等级为 `SHOULD_INTERVENE` 或 `MUST_INTERVENE` 时，动作不能只有 `NO_ACTION_MONITOR`。违反时必须进入一次定向修复，不能发布互相矛盾的决策包。
