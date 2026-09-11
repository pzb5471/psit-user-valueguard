# PSIT MVP 技术实施规格（AI 技术执行文档）

- 文档状态：LIVE_POC_AUTOMATED_GATE_PASSED；四模块、固定案例和真实模型自动结构门已完成，双人业务复核与最终人工演示待完成
- 适用阶段：10 天本机可运行 MVP
- 适用对象：M1 数据与存储、M2 AI 分析引擎、M3 业务服务与 API、M4 前端工作台
- 文档角色：PSIT MVP 唯一技术执行真源，内含 37 张开发 Task
- 使用规则：实现技术合同、领取 Task、编写代码和执行验收时，只读本文件即可。需求文档、技术专题、ADR、handoff 和历史对话只用于追溯，不能覆盖本文
- 执行规则：执行者领取一个 Task ID，只改该卡声明的范围；不得重新决定本文已经冻结的跨模块合同
- 更新日期：2026-09-11

## 1. 最终技术结论

PSIT MVP 采用单机、单进程、本地 Web 工作台。业务人员通过浏览器导入标准案例 ZIP，明确点击开始分析；FastAPI 在后台调度三个顺序阶段，真实调用 GLM-5.3-Flash；SQLite 保存批次、案例、阶段结果、模型调用、人工确认和当前状态；React 页面只从 FastAPI 读取业务结果。页面刷新、浏览器关闭后重新打开、程序中断后重新启动，都不能依赖前端内存恢复事实。

MVP 的最小闭环是：

1. 标准 ZIP 能被严格校验并完整导入。
2. 用户明确开始后，感知、归因、策略三个阶段真实调用 GLM。
3. 每个阶段结果先经过程序校验，再持久化；只有完整决策包能够发布给页面。
4. 页面能展示高价值客户结论、风险原因、证据和处理建议。
5. 运营人员能通过、修改后确认、驳回并给出判断，或标记证据不足。
6. 刷新能读回，重复请求不重复付费，中断后状态诚实且允许人工从头重跑。
7. 固定演示案例可以重复走完整链路，但不得被表述为真实客户关系、真实流失预测准确率或真实业务收益。

本期不采用 Claude Code Agent Teams 作为产品运行时，不采用 Streamlit，不引入分布式队列，也不建设生产级部署与运维体系。Claude Code Agent Teams 只可以作为开发协作工具。

## 2. 使用规则与当前状态

### 2.1 当前状态

| 对象 | 当前状态 | 这句话意味着什么 |
|---|---|---|
| 产品范围与业务闭环 | 已冻结 | 不再增加用户、页面、模态、动作或生产能力 |
| 技术架构与跨模块合同 | 已冻结在本文 | 四个模块直接按本文开发，不再从历史材料挑选方案 |
| 37 张 Task | 已定义 | 每张卡仍须在依赖满足后执行，不代表代码已经存在 |
| 四模块代码与 SQLite | 已完成确定性集成 | 应用、数据库、前端和测试模型流程可运行；不等于真实模型已验收 |
| `demo_batch_v1` 与 `acceptance_batch_v1` | 组包程序和 10+5 案例门已完成 | 运行 ZIP 不入 Git；新环境必须提供外部源数据并执行 `scripts/prepare-demo-data.ps1`，缺源时 M1-09 明确失败 |
| GLM-5.3-Flash 真实 PoC | 自动结构门已通过 | 最终 run_id `20260911T040909Z` 为 15/15 案例、45/45 阶段通过；两名验收者仍需复核 5 个验收案例 |
| MVP 可用性 | 尚待人工验收 | 自动技术链路已通过；双人业务复核与第 15.3 节人工演示完成后，才可以称为“核心链路可运行 MVP” |

`LIVE_POC_AUTOMATED_GATE_PASSED` 只表示真实模型结果通过结构、证据引用和动作边界等自动门，不表示两名业务验收者已经认可结果，也不表示最终人工演示已经完成。

### 2.2 最终裁决摘要

| 范围 | 本期唯一做法 |
|---|---|
| 产品运行时 | FastAPI 单进程内的 Python `RunService`；三个 Agent 是三组顺序职责、Prompt 和合同，不是三个常驻服务 |
| 案例输入 | `CaseInput v1` 不预写 `case_trigger`；感知阶段从现有证据还原事件 |
| 当前与历史 | `batches` 保存并随重跑更新当前投影；`batch_runs` 只保存首次批量运行历史 |
| 批次完成 | `COMPLETED` 表示批次分析结束，不表示全部案例已经人工确认 |
| 人工表单选项 | 不新增接口；仅在 `can_review=true` 时由 `CaseDetailView.review_options` 返回后端同源只读选项 |
| 结果发布 | 三阶段结果、当前运行指针、案例状态和批次投影在一个事务提交后，结果才对页面可见 |
| 模型门槛 | 15 个固定案例的 45 个阶段必须全部运行或留下明确失败；质量、耗时和费用阈值只能由真实 PoC 产生 |
| 本机启动 | 保留固定回环端口、运行目录锁、每次构建、迁移、启动恢复、健康检查和 Ctrl+C；其余启动器加固不进入本期 |
| 前端设计 | 三个业务页面遵守本文第 13 节的完整视觉与交互规则，不照搬营销页设计 |
| 团队协作 | M3-01 建立单仓库和统一质量入口，之后四个模块并行；一张 Task 对应一个主模块和一个可验收结果 |

### 2.3 执行词汇

| 词 | 本文含义 |
|---|---|
| AFK | 执行者可在依赖和输入齐全后独立编码并运行自动验收；仍需完成卡片列出的人工审查 |
| HITL | 必须有人提供密钥、承担模型费用、查看页面或作出业务质量判断，不能伪装成全自动完成 |
| Fake | 只在测试注入的模块替身，用于确定性验证；不得进入演示模式或业务页面 |
| PoC | 用固定案例真实调用 GLM，记录结构、质量、耗时、Token、错误和并发表现的可行性验证 |
| 密封答案 | 与运行 ZIP、产品目录和 Agent 输入物理分离的人工参考结果，只供验收程序和验收者读取 |
| 当前投影 | 页面此刻应该看到的批次、案例和人工结果；它可以随合法重跑或人工确认更新 |
| 历史记录 | 已发生的运行、阶段结果、模型尝试和审核记录，只追加、不覆盖 |
| 合同变更 | 会改变跨模块字段、枚举、接口、状态、费用上限、用户结果或验收含义的改动；必须独立处理并由受影响模块共同审查 |

## 3. 三类技术决定

### 3.1 必须冻结的跨模块合同

以下内容改变时，必须作为独立合同变更处理，并同步修改合同测试、OpenAPI、前端生成类型和受影响 Task：

| 范围 | 冻结内容 |
|---|---|
| 模块边界 | M1、M2、M3、M4 的职责、依赖方向和禁止穿透规则 |
| 数据合同 | CaseInput v1、PerceptionResult、AttributionResult、DecisionPackage 的字段边界与证据引用规则 |
| 分析合同 | 三阶段顺序、AnalysisRequest、AnalysisOutcome、内部事件、严格校验、一次定向修复和每阶段请求上限 |
| 业务枚举 | 案例状态、批次状态、运行状态、触发类型、介入等级、原因类别、人工确认结果和动作目录 |
| 持久化语义 | 九表逻辑 Schema、唯一约束、追加历史、当前指针、短事务、当前统计与历史统计 |
| HTTP 合同 | 十个接口、请求、响应 DTO、状态码、BusinessError、review_token 和 review_options |
| 状态与恢复 | 允许转换、禁止转换、完整发布条件、启动恢复、正常关闭和人工重跑 |
| 用户可见结果 | 三个页面、Mock 标记、证据边界、人工确认、刷新读回、1024px 最低可用和断网运行 |
| 验收真相 | 确定性自动测试与真实 GLM 验证分开；密封答案不进入运行环境；不删除失败案例 |

### 3.2 Task 内部实现默认值

以下值用于让开发直接开始。它们不是产品事实，也不是跨模块业务合同。Task 可以在不改变接口、费用上限、用户结果和验收含义的前提下调整；调整后必须更新同一模块测试和配置说明：

| 项目 | 初始默认值 |
|---|---|
| 演示地址 | 127.0.0.1:8000 |
| 开发前端地址 | 127.0.0.1:5173 |
| 案例并发 | 2，可在 1—3 内配置并通过 PoC 决定最终值 |
| 活动批次轮询 | 2 秒；页面进入后台暂停，回到前台立即刷新 |
| GLM 连接超时 | 10 秒 |
| GLM 单次完整响应上限 | 300 秒 |
| GLM 起跑参数 | 非流式、JSON 对象、thinking enabled、reasoning_effort high、do_sample false、max_tokens 4096 |
| SQLite | 外键开启、WAL、busy_timeout 5 秒、同步 Session、短事务 |
| 工具链 | Python 3.12、uv、Node.js 24、pnpm 11；精确依赖版本由锁文件在实际兼容性验证后确定 |
| 本机目录 | 项目根目录下 runtime_data |
| 日志 | 脱敏结构化 JSONL；是否轮换及轮换大小由 M3 Task 决定 |
| 内部实现名 | Repository 类名、SQLAlchemy 模型类名、线程池变量名、锁实现细节和内部文件拆分 |
| 上传上限 | 固定合格 ZIP 形成后，按最大合格包实际大小约两倍并向上取整 |

这些默认值一旦被正式 PoC 或共享配置采用，就必须由所有消费者读取同一配置，不允许前后端分别写死。

### 3.3 未来正式产品能力

以下能力不进入本期 Task：

- 登录、角色、权限、审计后台、多用户协作和租户隔离。
- 局域网、公网、云部署、HTTPS、域名、安装包、自动升级和企业密钥管理。
- Redis、Celery、多进程 Worker、分布式队列、流式输出和自动断点续跑。
- 实时 CRM、客服、物流、退款和补偿系统接入，以及处理动作自动执行。
- 生产监控、SLA、告警、异机备份、灾难恢复、数据删除与保留策略。
- 模型路由、多模型自动降级、训练、微调、RAG、向量库和研究级多模态融合。
- 音频、视频、实时行为流、真实留存提升、真实 ROI 和因果效果验证。

## 4. MVP 范围与完成定义

### 4.1 本期必须交付

| 能力 | 可见结果 | 完成证据 |
|---|---|---|
| 导入 | 用户上传一个标准 ZIP，看到文件名、案例数、证据数、校验结果和 Mock 标记 | 合格包完整导入；任一不合格文件导致整批拒绝；数据库和正式目录不留半成品 |
| 分析 | 用户明确点击开始后，案例进入分析中并在后台真实调用 GLM | 模型调用记录、阶段结果和业务状态能从 SQLite 读回 |
| 决策 | 页面展示高价值客户、风险摘要、主要原因、证据、介入等级、处理动作和沟通重点 | 结果引用当前案例证据，动作在目录内，程序规则通过 |
| 人工确认 | 用户能够通过、修改后确认、驳回并给出判断，或标记证据不足 | 结果幂等保存，旧 review_token 被拒绝，已完成案例只读 |
| 恢复 | 刷新、返回、关闭浏览器后重新打开，仍能回到同一批次和案例 | URL、FastAPI 和 SQLite 恢复页面，不依赖 localStorage 业务事实 |
| 中断处理 | 应用中断后不永久停在分析中，也不自动产生新模型费用 | 启动恢复将未完成运行标记为中断，案例可由人工从头重跑 |
| 演示 | 固定演示包能够重复走完导入、分析、查看、确认和刷新链路 | 确定性 E2E、真实 GLM PoC 和人工验收分别留下结果 |

### 4.2 明确不做

MVP 不提供暂停、取消、自动恢复、批次删除、案例删除、已完成人工结果修改、任意搜索、任意排序、模型参数页面、Prompt 页面、日志页面、动作目录管理页面或服务器文件路径导入。浏览器关闭不停止分析。

## 5. 数据与标准案例包

### 5.1 数据事实边界

当前数据是“一主两辅”。交易事实、售后对话和图片没有可证明的跨来源真实客户连接。固定案例使用 mock_mapped 关系，只用于产品流程验证。

每项内容必须区分：

| 身份 | 含义 | 允许用途 |
|---|---|---|
| observed | 数据源中直接存在的观察 | 展示、引用和派生 |
| derived | 由固定程序从观察复算的事实 | RFM、高价值结论、付款聚合、履约事实和排序 |
| simulated | 为演示建立且明确标记的组合关系 | 固定案例流程，不得当成真实客户关系 |

Agent 输出的事件、情绪、原因和策略不是源字段；它们是必须引用现有证据的判断。任何字段只有满足“现有来源、固定可复算、确定运行元数据、或有证据的必要 Agent 判断”之一，且存在明确消费者，才可以进入 v1。

### 5.2 现有数据基线与使用顺序

进入开发仓库后，源数据逻辑根目录固定记为 `source_data/ecommercedata-main/`。当前团队开工包已经按此结构保存数据；M1 的组包程序只能通过一个显式 `--source-root` 参数定位它，不能在代码中写成员电脑绝对路径。

| 数据 | 相对位置 | 本期用途 | 明确禁止 |
|---|---|---|---|
| 清洗后主表 | `dataprocessing/output/data_with_context.csv` | 唯一组案主入口；提供订单、客户、履约、付款、对话和图片引用 | 不能把 CSV 每行当案例，不能沿用旧绝对阈值 |
| 处理 Notebook | `dataprocessing/processing.ipynb` | 追溯已有清洗、RFM 和 Mock 映射方法 | 不能重新运行无固定随机种子的旧映射覆盖当前关系 |
| Olist 五张核心表 | `data/Olist-Brazilian-E-Commerce/` | 对清洗结果做同源核验和必要补漏 | 不重新建设完整原始数据治理，不引入新来源字段 |
| 客服任务 | `data/service_tasks.json` | 提取售后对话、图片引用及密封参考材料；文件实际为 JSONL | 答案性质字段不得进入运行包、Prompt 或模型上下文 |
| 图片 | `data/images/` | 固定案例实际引用的售后图片 | 不把完整图片库塞进运行 ZIP，不从文字反推图片内容 |
| JDDC 文本 | `data/JD-Customer-Service-Text/` | 客服文本辅助来源与清洗结果 | 不冒充 Olist 同一真实客户或订单 |
| E Commerce Dataset | `data/E-Commerce-Churn-Baseline/` | 独立流失方法参考 | 不按客户标识与 Olist 强行拼接，不作为当前案例行为证据 |

使用顺序固定为：先读清洗后主表；只有字段缺漏、关系核验或来源追溯确有需要时，才回到同源原始表；不再寻找新数据集。清洗后数据不是无用中间物，它承担订单级组案、RFM 计算、固定 Mock 映射和标准案例包生成的工程基线。

当前清洗后主表已经复核的事实如下。数字用于验证输入没有误读，不代表生产规模：

| 项目 | 当前值 |
|---|---:|
| 行数 | 103,886 |
| 唯一订单 | 99,440 |
| 唯一客户 | 96,095 |
| 字段数 | 19 |
| 有售后对话的订单 | 11,855 |
| 有图片的订单 | 540 |
| 同时有文本和图片的订单 | 540 |
| 图片引用总数 | 995 |
| 当前唯一图片引用 | 92 |

主表字段为 `order_id`、`customer_id`、`customer_unique_id`、`order_status`、五个订单与履约时间、`payment_sequential`、`payment_type`、`payment_installments`、`payment_value`、三个地理字段、`conversation`、`image_paths` 和一个无字段名旧索引列。组包时必须先按订单聚合付款、丢弃旧索引、把 `image_paths` 从 Python 列表字符串转成 JSON 数组，并剔除地理字段、付款方式与分期等 v1 不消费的内容。

### 5.3 `high_value_rule_v1`

RFM 在全部客户级交易快照上由确定性程序计算，先于固定案例筛选：

1. `snapshot_at` 取当前数据版本中最大的 `order_purchase_timestamp`。
2. `R` 为 `snapshot_at` 减去该客户最近一次下单时间的完整天数；R 越小，购买越近。
3. `F` 为该客户不同 `order_id` 的数量，不受付款拆行影响。
4. `M` 为该客户所有 `payment_value` 的总和；付款拆行先按真实付款记录求和，不重复复制订单总额。
5. `P75(R)`、`P80(M)`、`P50(M)` 使用当前客户快照的线性分位数计算；判断使用 `<=` 或 `>=`，所以等于边界的客户全部纳入。

高价值判定唯一公式为：

    R <= P75(R)
    AND
    (M >= P80(M) OR (F >= 2 AND M >= P50(M)))

对当前 `data_with_context.csv` 的复算结果是：`snapshot_at=2018-10-17T17:30:18`、`P75(R)=397`、`P80(M)=209.604`、`P50(M)=108.0`，96,095 名客户中 15,208 名满足规则。M1-09 必须把源文件哈希、客户数、三个实际边界、计算日期、规则版本、逐客户 R/F/M、判定结果和判定理由写入可复算内部产物；数据版本变化时重新计算，不把这里的数值写死进业务代码。

旧 Notebook 中的 `F>=10`、`M>=800`、`R<=500` 只供历史对照，不能成为产品规则。RFM 只判断当前 Mock 数据里的相对客户价值：感知和归因阶段看不到高价值结论，策略阶段只读取 `is_high_value` 和业务化价值摘要，页面只显示结论，不显示公式、分数、权重和阈值。

### 5.4 标准 ZIP

ZIP 根目录固定包含：

    manifest.json
    cases/
    assets/
    checksums.json

cases 中每个案例保存一份 CaseInput v1。assets 只包含这些案例实际引用的图片。manifest 和案例只能使用相对路径。原始大 CSV、完整图片库和验收答案不能进入运行 ZIP。

`manifest.json` 只允许以下字段：`schema_version="batch_manifest.v1"`、`data_version`、`batch_id`、`package_type`（`DEMO` 或 `ACCEPTANCE`）、`is_mock=true`、`source_snapshot_at`、`case_files`、`case_count`、`evidence_count`。`case_files` 按路径升序排列；数量必须与实际 `cases/*.json` 一致。

`checksums.json` 是“相对路径 → 小写 SHA-256”的对象，必须覆盖 manifest、全部案例和全部图片，但不包含自身。ZIP 内文件按相对路径升序写入，JSON 使用 UTF-8、LF、稳定键顺序和无意义空白最小化；ZIP 条目的时间戳、权限和压缩参数固定。相同输入连续组包必须得到相同文件清单、内容哈希和 ZIP 哈希。

固定数据版本为 mock_dataset_v1。项目提供互不重叠的 demo_batch_v1 10 个案例和 acceptance_batch_v1 5 个案例。任何数据或映射变化必须产生新的 data_version 和 batch_id，不能覆盖旧版本。

导入规则：

- 一次只接收一个 ZIP。
- 同一 package_sha256 再次导入，返回已有批次，不重复落库。
- batch_id 全局唯一；已有 batch_id 对应不同内容时返回 BATCH_ID_CONFLICT。
- case_id 在批次内唯一；evidence_id 在案例内唯一。
- ZIP 内任一文件、Schema、关系、校验值或路径不合格，整批拒绝。
- 图片只接受 JPG、JPEG、PNG 和 GIF；GIF 原文件保留，模型使用静态首帧。
- 导入成功只生成 PENDING_ANALYSIS，不自动调用模型。
- 每批最多 20 个案例。

导入器必须递归拒绝以下答案或答案泄漏字段：

    mood
    reason
    solution
    image_verification
    key_answer
    label
    database_gt
    trajectory
    user_profile_st1
    user_profile
    question_type

未规范化的 user_address、database 和重复 first_query 也不得进入运行环境。运行包只保存脱敏对话；固定 15 个案例必须逐条人工检查地址、手机号、订单号、物流单号和 URL。

### 5.5 CaseInput v1

顶层字段只允许：

| 字段 | 内容 |
|---|---|
| schema_version | 案例合同版本 |
| data_version | 固定数据版本 |
| batch_id | 批次公开标识 |
| case_id | 批次内稳定案例标识 |
| data_identity | 当前案例的数据身份 |
| primary_order | 源订单标识、脱敏展示标识、状态、下单时间、源中存在的履约时间、聚合付款总额 |
| customer | 由 customer_unique_id 确定生成的脱敏 customer_ref |
| customer_value | 高价值结论、规则版本、快照时间、R、F、M、分位边界、判定理由和内部来源 |
| evidence | text_items、image_items、behavior_items |
| provenance | 来源、映射和组包追溯信息 |

禁止增加 case_trigger、modality_status、currency、payment_parts、simulated_wait_minutes、behavior_change、window_start、window_end、城市、州和邮编。

以下嵌套字段名和类型属于 v1 合同，不由 Task 自行改名：

| 对象 | 必填字段 | 可选字段与规则 |
|---|---|---|
| `primary_order` | `source_order_id: str`、`order_display_id: str`、`order_status: str`、`order_purchase_timestamp: datetime`、`payment_total: Decimal` | `order_approved_at`、`order_delivered_carrier_date`、`order_delivered_customer_date`、`order_estimated_delivery_date`；仅源数据存在时出现 |
| `customer` | `customer_ref: str` | 不保存城市、州、邮编；源 `customer_unique_id` 只进 provenance |
| `customer_value` | `is_high_value: bool`、`rule_version="high_value_rule_v1"`、`snapshot_at: datetime`、`recency_days: int`、`frequency_orders: int`、`monetary_total: Decimal`、`r_p75: Decimal`、`m_p80: Decimal`、`m_p50: Decimal`、`decision_reason: str`、`source_ref: SourceRef` | 无 |
| `provenance` | `builder_version: str`、`source_manifest_sha256: str`、`mapping_manifest_sha256: str`、`source_refs: list[SourceRef]` | 无自由说明字段；Mock 关系由可复算清单表达 |
| `SourceRef` | `dataset: str`、`relative_path: str`、`record_key: str` | `field: str`；路径必须相对 source root，不得含绝对路径或 `..` |

`data_identity` 在 `mock_dataset_v1` 固定为 `simulated`。每条原始证据仍分别标记 `observed` 或 `derived`；`relation_identity` 在当前固定组合中为 `mock_mapped`。金额使用 Python `Decimal` 计算并按十进制定点字符串序列化，不能用二进制浮点累计付款。

customer_value 的完整内容只供确定性程序复算和追溯。Agent 与业务页面只读取高价值结论，不读取 RFM 数值、权重、阈值和计算过程。付款金额可用于内部追溯，页面必须说明“Mock 数据金额，源数据未提供币种”，不得显示人民币或猜测币种。

### 5.6 证据合同

三类证据共同具有 evidence_id、identity、relation_identity、source_ref 和 content_hash。

| 类型 | 必需内容 | 约束 |
|---|---|---|
| text_items | `sequence_no: int`、`role: CUSTOMER\|SERVICE_AGENT`、`text: str` | 源数据没有消息时间，不设置 occurred_at；文本必须已经脱敏 |
| image_items | `asset_relative_path: str`、`media_type: image/jpeg\|image/png\|image/gif` | `content_hash` 即原文件 SHA-256；路径不得越界；同一案例重跑编号不变 |
| behavior_items | `fact_type`、严格标量 `value` | 派生事实按需增加 `calculation_rule`；模型不得修改数值或重算 RFM |

`identity` 只允许 `observed`、`derived`、`simulated`；当前运行证据不使用 `simulated` 伪造事实，模拟性通过 `relation_identity=mock_mapped` 表达。`fact_type` 只允许 `HIGH_VALUE_CUSTOMER`、`ORDER_STATUS`、`ORDER_PURCHASED_AT`、`ORDER_APPROVED_AT`、`ORDER_DELIVERED_TO_CARRIER_AT`、`ORDER_DELIVERED_TO_CUSTOMER_AT`、`ORDER_ESTIMATED_DELIVERY_AT`、`ORDER_PAYMENT_TOTAL`。付款金额只供来源追溯和页面说明，不进入三个 Agent 的模型上下文。

所有合同统一使用 Pydantic 严格模式、`extra="forbid"` 和禁止宽松类型转换；ID 为 1—128 个可打印非空字符，SHA-256 为 64 位小写十六进制，数组保持输入顺序且不得含重复 `evidence_id`。可选字段不适用时省略，不用 `null`、空数组或套话占位。

图片可以缺失，但案例至少包含一条有效脱敏客户售后消息。只有固定案例中已经人工核验、与对话语义不冲突的订单和履约事实，才能进入 Agent 受限视图。

## 6. 总体架构与模块边界

    M4 React 前端工作台
              |
              | REST / OpenAPI
              v
    M3 FastAPI 业务服务与运行编排
              |
              +--------------------+
              |                    |
              v                    v
    M1 数据与存储          M2 AI 分析引擎
    SQLite / 文件          GLM-5.3-Flash

技术栈固定如下。精确补丁版本以 M3-01 实际兼容性验证后提交的锁文件为准，不能由各模块自行选择第二套框架：

| 层 | 采用技术 | 用途 |
|---|---|---|
| 语言与依赖 | Python 3.12、uv、`pyproject.toml`、`uv.lock` | 后端、数据、Agent 和测试的统一运行环境 |
| HTTP 与合同 | FastAPI、Pydantic v2、pydantic-settings | REST、OpenAPI、严格输入输出和配置校验 |
| 持久化 | SQLAlchemy 2 同步模式、Alembic、SQLite WAL | 九表、迁移、短事务、当前投影和追加历史 |
| 模型接入 | 智谱官方 `zai-sdk`、GLM-5.3-Flash | 文本与图片调用；只允许通过一个 `GlmClient` |
| 后台执行 | Python `ThreadPoolExecutor` | 单进程内有界案例并发，不引入外部队列 |
| 前端 | React、TypeScript、Vite、Ant Design | 三页面本地 Web 工作台 |
| 前端状态与接口 | React Router、TanStack Query、Ant Design Form、openapi-typescript、openapi-fetch | URL 状态、服务端缓存、表单和生成式 API 客户端 |
| 后端质量 | Ruff、Pyright、Pytest、Alembic Schema 检查 | 格式、静态类型、单元/合同/集成测试和迁移验证 |
| 前端质量 | ESLint、TypeScript、Vitest、React Testing Library、MSW、Playwright | 类型、组件、接口替身和浏览器旅程 |
| 本机入口 | Windows PowerShell 脚本 | 初始化、开发、测试和单入口演示启动 |

固定规则：

- M1 与 M2 互不调用。
- M4 只通过 M3 的 /api/v1 获取产品能力。
- M3 只通过 M1 和 M2 的公开合同调用，不导入内部实现。
- 共享合同只依赖 Python 标准库、typing 和 Pydantic，不导入 FastAPI、SQLAlchemy、智谱 SDK 或前端状态。
- 跨模块传递 Pydantic 对象、Protocol 或受控文件流，不传 ORM、Session、SDK 响应、本机路径或 React 状态。
- M3 是唯一装配点，负责依赖注入、状态机、后台执行和 HTTP。
- Fake 只存在于测试边界；缺少 ZAI_API_KEY 时分析不可用，但历史读取仍可用，绝不自动切换假模型。

模块根目录和共享合同目录属于冻结边界；模块内部子目录和具体类名属于 Task 默认值：

    backend/app/contracts/
    backend/app/modules/data/
    backend/app/modules/analysis/
    backend/app/modules/application/
    frontend/
    tests/
    config/
    scripts/

不建立承接任意业务逻辑的 common、utils 或 shared 杂物目录。

## 7. 跨模块业务合同

### 7.1 Agent 输出

PerceptionResult 顶层只允许：

- schema_version
- case_id
- events
- image_observations
- emotion
- missing_evidence

事件只保存事件编号、类别、摘要、陈述状态、解决状态、支持证据，以及按需出现的冲突证据和不确定性。陈述状态区分客户声称、客服陈述或承诺、客户确认结果、图片直接观察和程序派生事实。解决状态只允许已解决、未解决、无法确认。

每张输入图片必须对应一条 ImageObservation，只保存图片证据编号、分析状态、最多三条可观察事实、与客户陈述的关系、关联文本证据和按需出现的不确定性。关系只允许相互支持、相互冲突、补充信息、无法判断。不得输出检测框、坐标、概率、Embedding 或特征向量。

emotion 只允许平静、不耐烦、无法判断，并必须引用客户文本证据。不得根据客服语气推断客户情绪。

AttributionResult 顶层只允许：

- schema_version
- case_id
- risk_summary
- primary_cause
- 按需出现的 alternative_cause

原因对象保存受控类别、解释、支持证据，以及按需出现的反证和不确定性。只有证据确实同时指向另一类原因时，才允许一个备选原因。原因不能被表述为已经证明的因果事实。

DecisionPackage 顶层只允许：

- schema_version
- case_id
- intervention_level
- priority_reason
- actions
- communication_points
- 按需出现的 caution_note

每个动作保存 action_type、具体描述、原因、支持证据，以及按需出现的前置条件。动作最多三项，沟通重点最多三项。requires_human_approval 由产品门禁统一执行，不由模型重复输出。

### 7.2 冻结枚举

案例业务状态：

| 合同值 | 页面文字 |
|---|---|
| PENDING_ANALYSIS | 待分析 |
| ANALYZING | 分析中 |
| PENDING_REVIEW | 待人工确认 |
| COMPLETED | 已完成 |
| PROCESSING_ERROR | 处理异常 |

批次业务状态：

| 合同值 | 页面文字 |
|---|---|
| PENDING_ANALYSIS | 待开始分析 |
| ANALYZING | 分析中 |
| COMPLETED | 分析已完成 |
| COMPLETED_WITH_ERRORS | 分析完成，存在异常 |

案例运行内部状态：

    STARTING
    PERCEPTION_RUNNING
    ATTRIBUTION_RUNNING
    STRATEGY_RUNNING
    SUCCEEDED
    FAILED
    INTERRUPTED

批次运行内部状态：

    STARTING
    RUNNING
    COMPLETED
    COMPLETED_WITH_ERRORS
    FAILED
    INTERRUPTED

触发类型：

    BATCH
    MANUAL_RERUN

介入等级：

| 合同值 | 页面文字 | 排序 |
|---|---|---:|
| MUST_INTERVENE | 必须介入 | 1 |
| SHOULD_INTERVENE | 建议介入 | 2 |
| NO_IMMEDIATE_INTERVENTION | 暂不介入 | 3 |

六个业务原因：

    LOGISTICS_FULFILLMENT
    PRODUCT_ISSUE
    RETURN_REFUND
    SERVICE_COMMUNICATION
    PRICE_OR_BENEFIT
    OTHER

INSUFFICIENT_EVIDENCE 是归因无法可靠判断时的非原因兜底值，不是第七种业务原因，也不能并入 OTHER。

人工确认结果：

    APPROVED
    MODIFIED_AND_APPROVED
    REJECTED_WITH_JUDGMENT
    INSUFFICIENT_EVIDENCE

### 7.3 动作目录

动作目录固定为 action_catalog.v1.json，只读且无管理页面。为消除 M2、M3、M4 各自造代码的风险，v1 的 action_type 固定如下：

| action_type | 业务含义 |
|---|---|
| EVIDENCE_CHECK | 补充或核实图片、物流、订单或退款证据 |
| CUSTOMER_CONTACT | 建议人工联系客户，并给出沟通重点 |
| FULFILLMENT_ESCALATION | 建议升级物流或订单履约处理 |
| REPLACEMENT_RETURN_REFUND_CHECK | 建议补发、退货或退款核验 |
| APOLOGY_COMPENSATION_RETENTION_REQUEST | 提交但不执行道歉、补偿或挽留申请 |
| NO_ACTION_MONITOR | 暂不采取动作，并说明观察或复查理由 |

系统不得生成具体补偿金额、权益承诺、退款完成状态或真实执行结果。目录在启动时校验版本、代码唯一性和禁止内容。每次策略运行记录所使用的目录版本。

### 7.4 最低介入规则

Strategy Agent 提出等级，程序执行最低介入规则：

- 未解决的明显损失、严重履约异常、商品损坏、错漏发、未到货和退货退款争议，不能成为 NO_IMMEDIATE_INTERVENTION。
- 严重问题存在证据冲突或证据不足时，至少为 SHOULD_INTERVENE，并明确需要人工核验。
- 只有问题已经确认解决，或当前没有可执行风险事项，才允许 NO_IMMEDIATE_INTERVENTION。
- 高价值客户身份本身不能单独触发 MUST_INTERVENE。

模型等级低于程序底线时，程序直接提高等级并保存原值、最终值和原因，不再次调用模型，不改写风险原因和动作。

## 8. M1 数据与存储合同

M1 对 M3 提供五组公开能力。公开 Protocol 名称冻结；实现类名和方法内部拆分不冻结。

| Protocol | 输入 | 输出与责任 | 禁止事项 |
|---|---|---|---|
| BatchImportGateway | ZIP 文件流、原文件名、内容长度、trace_id | 导入摘要或逐项拒绝；幂等识别；原子发布批次 | 不接受服务器路径，不调用模型，不留下半批次 |
| CaseQueryGateway | batch_id、case_id、固定筛选和分页 | CaseInput v1、批次投影、队列投影、详情投影 | 不返回 ORM，不从任意 JSON 临时排序 |
| EvidenceGateway | batch_id、case_id、evidence_id | 受控图片流、真实媒体类型、业务文件名 | 不返回绝对路径，不允许跨案例或路径穿越 |
| RunStore | 批次与案例运行命令、阶段事件、成功或失败结果 | 幂等创建运行、保存尝试与阶段、原子发布、记录异常、恢复中断 | 等待 GLM 时不持有事务，不覆盖旧运行 |
| ReviewStore | 四种人工确认命令、submission_id、review_token | 幂等人工结果和当前业务结果 | 不重复保存系统原结果，不接受过期或已完成修改 |

ReviewStore 中“系统原结果”通过 reviews.case_run_id 引用不可变的 stage_results，不在 reviews 表复制第二份决策包。

M3 决定“是否允许、下一状态是什么”；M1 负责“在一个短事务中完整写入”。M3 不提交 Session，M1 不自行发明状态转换。

## 9. M2 AI 分析合同

### 9.1 唯一入口

M2 只公开一个同步阻塞入口：

    AnalysisEngine.analyze_case(
        request: AnalysisRequest,
        event_sink: AnalysisEventSink
    ) -> AnalysisOutcome

AnalysisRequest 只组合：

- trace_id
- 内部 case_run_id
- CaseInput v1
- 三份结果合同版本
- 三阶段 Prompt 版本
- action_catalog_version

M2 不能根据数据库、其他案例、密封答案或页面状态补充上下文。

AnalysisOutcome 是严格的成功或失败联合结果：

- 成功：同一 case_id 的 PerceptionResult、AttributionResult、DecisionPackage。
- 失败：稳定错误分类、失败阶段、是否耗尽允许尝试和 trace_id。

证据不足只要结果结构完整，就属于成功并进入 PENDING_REVIEW，不属于技术失败。

AnalysisEventSink 依次接收五类事件：

    STAGE_STARTED
    MODEL_ATTEMPT_FINISHED
    STAGE_RESULT_VALIDATED
    STAGE_FAILED
    ANALYSIS_COMPLETED

事件用于 M3 调用 M1 保存运行记录。事件持久化失败时立即停止当前案例，不能继续运行后假装记录完整。

### 9.2 阶段最小权限

| 阶段 | 允许读取 | 禁止读取 |
|---|---|---|
| 感知 | 当前案例脱敏对话、图片、已核验订单与履约事实、case_id、可引用证据编号 | 高价值结论、RFM、风险答案、动作目录、其他案例、密封答案 |
| 归因 | PerceptionResult、其中实际引用的客户文本与订单事实、图片观察、证据编号 | 原始图片、完整原始对话、高价值结论、RFM、动作目录、策略结果 |
| 策略 | PerceptionResult、AttributionResult、高价值结论、获准证据编号、动作目录、最低介入规则 | 原始图片、完整原始对话、RFM 过程、其他案例、密封答案 |

高价值结论只允许影响介入优先级和处理方式，不能反向改变事件、情绪或风险原因。

### 9.3 真实 GLM 调用

- 模型固定为 glm-5.3-flash。
- 只通过一个 GlmClient 封装官方 zai-sdk。
- 同一案例严格按感知、归因、策略顺序调用；第二、第三阶段不重复发送原图和完整对话。
- 不同案例由 M3 有界并发，同一案例三个阶段不并行。
- 关闭 SDK 自动重试，由应用统一记录与控制。
- 连接中断、读取超时、HTTP 429 和 HTTP 5xx 最多重试两次。
- 401、403、请求参数、图片格式、图片大小和输入合同错误不重试。
- 模型已经返回但结构或硬规则不合格时，只允许一次带具体错误的定向修复。
- 每阶段供应商请求总数最多四次：首次一次、网络重试最多两次、结构修复最多一次；修复请求发生网络错误后不再重试。
- 正常路径每案例三次请求。失败案例停止后续阶段，不影响同批其他案例。

每次调用保存模型名、Prompt 版本、请求清单、尝试序号、状态、响应或错误、开始结束时间、耗时和供应商实际返回的可用 Token 计数。日志不重复保存供应商完整响应。

### 9.4 严格校验

每个阶段按顺序执行：

1. JSON 解析。
2. Pydantic 严格字段与类型校验，禁止额外字段和宽松转换。
3. 枚举与 case_id 校验。
4. evidence_id 必须属于当前案例和当前阶段允许集合。
5. 跨阶段引用校验。
6. 隐藏答案与禁止内容校验。
7. 动作目录、数量和最低介入规则校验。

结构通过但业务仍有不确定性时进入人工确认，不因为主观偏好重新采样。

## 10. M3 业务服务、状态与恢复

### 10.1 后台执行

FastAPI 生命周期内只创建一个 ThreadPoolExecutor。一个案例运行对应一个 Future。全系统只允许一个活动的首次批次运行；同一案例只允许一个活动运行。数据库唯一约束是最终保护，按钮禁用和应用锁不能代替数据库约束。

开始批次和案例重跑立即返回 202，不等待 GLM。浏览器刷新、关闭或停止轮询都不影响后台任务。

### 10.2 案例状态机

| 当前状态 | 动作或结果 | 新状态 |
|---|---|---|
| PENDING_ANALYSIS | 所属批次开始 | ANALYZING |
| ANALYZING | 完整决策包原子发布 | PENDING_REVIEW |
| ANALYZING | 合同完整的证据不足结果发布 | PENDING_REVIEW |
| ANALYZING | 技术失败、请求耗尽或中断 | PROCESSING_ERROR |
| PENDING_REVIEW | 任一合法人工确认 | COMPLETED |
| PENDING_REVIEW | 人工重新分析 | ANALYZING |
| PROCESSING_ERROR | 人工重新分析 | ANALYZING |

禁止：

- PENDING_ANALYSIS 不能走单案例重跑。
- COMPLETED 不允许重跑、重新审核或无痕修改。
- 证据不足不能进入 PROCESSING_ERROR。
- v1 不增加停止、暂停、取消、恢复和自动重试业务状态。

### 10.3 批次状态与统计

批次状态由当前案例推导：

| 状态 | 判断 |
|---|---|
| PENDING_ANALYSIS | 所有案例待分析，首次批量分析未开始 |
| ANALYZING | 至少一个当前案例正在分析 |
| COMPLETED | 没有分析中和处理异常案例，所有案例均已有完整系统结果或人工结果 |
| COMPLETED_WITH_ERRORS | 没有分析中案例，至少一个当前案例处理异常 |

batches.case_count 是总案例数。batches.analysis_succeeded_count 是当前处于 PENDING_REVIEW 或 COMPLETED 且存在完整决策包的案例数。batches.error_count 是当前处于 PROCESSING_ERROR 的案例数。单案例重跑开始、成功或失败时，案例状态和三项当前投影在同一短事务更新。

batch_runs 只保存首次批量分析的历史统计。MANUAL_RERUN 不创建伪批次运行，不修改已经结束的 batch_runs。

### 10.4 完整发布

结果只有同时满足以下条件才对业务页面可见：

1. 三个阶段结果均通过合同和程序规则。
2. 最终阶段结果、case_run 成功状态、cases.current_case_run_id 和案例 PENDING_REVIEW 状态在同一事务提交。
3. batches 当前状态和计数在同一事务内保持一致。

阶段结果已经写入，但发布事务没有提交，不算完整结果。业务 DTO 不允许拼接半程阶段结果。

### 10.5 启动恢复

应用取得单实例锁并完成数据库迁移后、HTTP 开放前，执行一次幂等恢复检查：

1. 找出仍处于活动状态的 case_runs，标记为 INTERRUPTED 并记录结束时间。
2. 若该运行没有作为一个完整结果被原子发布，案例进入 PROCESSING_ERROR，错误为 APP_INTERRUPTED。
3. 找出仍处于 STARTING 或 RUNNING 的 batch_runs，标记为 INTERRUPTED。
4. 保留全部阶段结果、模型调用、错误和旧历史。
5. 重算受影响批次的当前状态和计数。
6. 恢复事务提交后，才开放 HTTP。

恢复检查不从中间阶段续跑，不自动建立新运行，不调用 GLM。运营人员通过现有重跑入口从头分析。

### 10.6 正常关闭

Ctrl+C 触发：

1. 拒绝新的开始和重跑请求。
2. 取消尚未开始的 Future，并把对应运行标为 INTERRUPTED。
3. 当前 GLM 请求等待返回或超时。
4. 当前请求与记录完成后，不再开始下一阶段。
5. 已满足完整发布条件的结果正常发布；其他运行进入中断。
6. 关闭线程池、日志和数据库资源，释放单实例锁。

本期不实现业务关机按钮、无认证关机接口或 stop.ps1 控制协议。

## 11. SQLite 与文件持久化

### 11.1 九表逻辑 Schema

字符串长度、索引名称、ORM 类名和迁移文件名不冻结；表、字段、唯一性和业务含义冻结。

| 表 | 独立列 |
|---|---|
| data_versions | id、data_version、source_snapshot_ref、source_manifest_sha256、provenance_json、created_at |
| batches | id、batch_id、data_version_id、schema_version、package_sha256、package_relative_path、status、case_count、analysis_succeeded_count、error_count、current_batch_run_id、imported_at、updated_at |
| cases | id、batch_id、case_id、schema_version、case_input_json、customer_display_id、is_high_value、status、system_intervention_level、final_intervention_level、current_case_run_id、current_review_id、imported_at、updated_at |
| evidence | id、case_id、evidence_id、modality、sequence_no、identity、relation_identity、source_ref_json、content_hash、occurred_at、relative_path、media_type、payload_json |
| batch_runs | id、run_id、batch_id、status、total_case_count、analysis_succeeded_count、error_count、started_at、finished_at、updated_at |
| case_runs | id、run_id、case_id、batch_run_id、previous_case_run_id、trigger_type、status、current_stage、error_code、error_stage、error_detail_json、started_at、finished_at、created_at、updated_at |
| stage_results | id、case_run_id、stage_name、contract_version、result_json、result_sha256、created_at |
| model_calls | id、call_id、case_run_id、stage_name、attempt_no、model_name、prompt_version、request_manifest_json、status、response_json、error_json、started_at、finished_at、latency_ms、可选 Token 计数 |
| reviews | id、review_id、submission_id、case_id、case_run_id、outcome、final_intervention_level、final_cause_json、final_actions_json、review_reason、created_at |

除 cases.case_id、batches.batch_id 等明确公开标识外，关系列使用内部整数外键。业务 API 不返回整数主键。

唯一性：

- data_version、batch_id、run_id、review_id、submission_id 全局唯一。
- case_id 在批次内唯一。
- evidence_id 在案例内唯一。
- 同一 case_run 和 stage_name 只有一份通过校验的 stage_result。
- v1 每案例最多一份正式 review。
- 全系统最多一个活动 batch_run；同一案例最多一个活动 case_run。

### 11.2 保存规则

- 每个 API 请求和后台案例任务使用独立同步 Session，不能跨线程共享。
- GLM 等待期间不打开数据库事务。
- 阶段最终合格结果保存在 stage_results；修复和重试过程保存在 model_calls。
- 旧 case_run、stage_results、model_calls 和 reviews 只追加、不覆盖。
- 图片不存 SQLite BLOB，只保存相对运行目录的路径、媒体类型和哈希。
- 程序时间保存为带毫秒的 UTC ISO 8601，页面转换为北京时间。
- 源数据没有发生时间时不补造。

### 11.3 运行目录

默认目录相对项目根目录解析：

    runtime_data/
      psit.db
      psit.lock
      imports/tmp/
      batches/
      logs/

允许 config/local.toml 显式覆盖为可写本机绝对目录，但不得使用 UNC 网络路径，不得失败后静默切换目录。数据库和 API 只保存或返回相对路径，业务页面不显示本机绝对路径。

MVP 启动顺序：

1. 读取并校验配置、ZAI_API_KEY 状态、运行目录和端口。
2. 取得运行目录单实例锁。
3. 构建当前前端；失败停止，不提供旧页面。
4. 使用 Alembic 创建或升级数据库；失败停止，不删除或自动重建现有数据库。
5. 执行中断恢复检查。
6. 由 FastAPI 提供静态页面和 /api/v1。
7. 健康检查通过后显示可访问地址。

本期不要求构建内容指纹缓存、dist 原子切换、自动打开浏览器、导入隔离区保留策略、自动备份轮换或实例级 stop.ps1。重要演示前的数据保护通过停止应用后复制完整 runtime_data 目录完成；正式迁移备份和灾难恢复属于后续加固。

## 12. HTTP API v1

请求和响应使用 snake_case。FastAPI Pydantic 是 OpenAPI 真源。M4 用 openapi-typescript 生成并提交 TypeScript 类型，用 openapi-fetch 请求；不得手写第二套 DTO。

### 12.1 十个固定接口

| 方法 | 地址 | 成功 |
|---|---|---|
| POST | /api/v1/batches | 新建 201，重复包 200；BatchWorkspaceView |
| GET | /api/v1/batches | 200 BatchListView |
| GET | /api/v1/batches/{batch_id} | 200 BatchWorkspaceView |
| POST | /api/v1/batches/{batch_id}/runs | 202 BatchWorkspaceView |
| GET | /api/v1/batches/{batch_id}/cases | 200 CaseQueueView |
| GET | /api/v1/batches/{batch_id}/cases/{case_id} | 200 CaseDetailView |
| POST | /api/v1/batches/{batch_id}/cases/{case_id}/reruns | 202 CaseDetailView |
| POST | /api/v1/batches/{batch_id}/cases/{case_id}/reviews | 新建 201，幂等命中 200；ReviewResultView |
| GET | /api/v1/batches/{batch_id}/cases/{case_id}/evidence/{evidence_id}/content | 200 图片流 |
| GET | /api/v1/health | 200 HealthView |

开始批量分析和重跑没有 JSON 请求体。模型参数、并发、Prompt 和运行编号不能由页面传入。

列表规则：

- 批次列表 limit 默认 20，案例列表默认 50，均为 1—100；offset 默认 0。
- 批次按 imported_at 倒序，再按 batch_id 稳定排序。
- 案例只允许一个 status 和一个 intervention_level 筛选。
- 案例始终按最终人工等级或系统等级、imported_at、case_id 排序，页面不能传 sort_by。

### 12.2 业务 DTO

BatchWorkspaceView：

- batch_id
- source_filename
- is_mock
- status
- case_count
- evidence_count
- analysis_succeeded_count
- error_count
- imported_at
- can_start_analysis
- 按需出现 analysis_unavailable_message

source_filename 从已保存包文件名读取，is_mock 从数据身份读取，evidence_count 由 evidence 表计数；不为这三个显示值新增业务源字段。

BatchListView 只包含 items: list[BatchWorkspaceView] 和 total。

CaseQueueItemView：

- case_id
- customer_display_id
- is_high_value
- 按需出现 risk_summary
- 按需出现 intervention_level
- 按需出现 priority_reason
- status
- has_evidence_conflict
- has_insufficient_evidence
- has_modality_failure

三个标记均由当前有效结果或当前运行错误确定：出现明确冲突证据时 has_evidence_conflict=true；主要原因使用非原因兜底值或缺失证据阻止可靠判断时 has_insufficient_evidence=true；当前运行因证据文件读取、图片格式、图片处理或相应模型处理失败而进入 PROCESSING_ERROR 时 has_modality_failure=true。正常缺少可选图片不属于模态技术失败。

CaseQueueView 只包含 items: list[CaseQueueItemView] 和 total。

CaseDetailView：

- batch_id
- case_id
- customer_display_id
- is_high_value
- customer_value_summary
- status
- 按需出现 intervention_level
- 按需出现 risk_summary
- 按需出现 primary_cause
- 按当前结果出现 actions
- 按当前结果出现 communication_points
- 按需出现 uncertainty
- 按需出现 missing_evidence
- 按当前结果出现 cited_evidence
- is_mock
- 按需出现 review_result
- 只在 `status=PROCESSING_ERROR` 时出现 `processing_error`
- can_rerun
- can_review
- 只在 can_review=true 时出现 review_token
- 只在 can_review=true 时出现 review_options

cited_evidence 中每项只返回 evidence_id、modality、业务 label，以及按证据类型出现的脱敏文本或可显示摘要。图片正文由 M4 使用现有 batch_id、case_id、evidence_id 调用受控证据接口取得，不增加 content_url 字段。业务 DTO 不返回本机路径、哈希、内部数据身份或来源 JSON。

review_options 固定为：

- intervention_levels：三档 value 与中文 label。
- cause_categories：六个业务原因的 value 与中文 label，不含 INSUFFICIENT_EVIDENCE。
- action_catalog_version。
- action_types：六项 action_type 与中文 label。

review_options 是后端冻结枚举和动作目录的只读投影，不是外部数据，不增加接口数量，也不建立配置管理能力。

`processing_error` 只包含 `code`、中文 `message`、业务化 `stage`、`next_action` 和 `trace_id`。`stage` 只允许 `INPUT_PREPARATION`、`EVIDENCE_PROCESSING`、`AI_ANALYSIS`、`RESULT_PERSISTENCE`、`APP_RECOVERY`，不得把感知、归因、策略等内部阶段直接展示给运营人员。

ReviewResultView：

- outcome
- 按结果出现 final_intervention_level
- 按结果出现 final_cause
- 按结果出现 final_actions
- 按需出现 execution_note
- 按需出现 review_reason
- created_at

HealthView：

- app_status
- database_status
- analysis_status
- message

健康接口成功返回时 app_status 和 database_status 均为 READY；analysis_status 只允许 AVAILABLE 或 UNAVAILABLE。缺少密钥或真实模型健康检查失败时使用 UNAVAILABLE，并通过 message 给出业务可理解说明。应用或数据库尚未就绪时不提前开放 HTTP。

业务 DTO 不返回 RFM 过程、data_version、schema_version、数据库主键、batch_run_id、case_run_id、阶段名、Prompt、Token、模型参数、供应商响应、本机路径、文件哈希、日志或原始 JSON。

### 12.3 人工确认请求

四种请求共同携带 submission_id、review_token 和 outcome。

| outcome | 必填 | 禁止 |
|---|---|---|
| APPROVED | 共同字段 | 另一份人工结果和审核原因 |
| MODIFIED_AND_APPROVED | final_intervention_level、final_cause、final_actions、修改原因；执行说明按需 | 目录外动作、自由 JSON |
| REJECTED_WITH_JUDGMENT | final_intervention_level、final_cause、final_actions、驳回原因；执行说明按需 | 只有驳回而没有人工判断 |
| INSUFFICIENT_EVIDENCE | 证据缺口说明 | 确定原因和处理动作 |

submission_id 由前端为一次业务提交生成 UUID，网络重试必须复用。相同 submission_id 返回第一次保存结果。review_token 不可读、不展示，不是登录凭证；结果被重跑替换后 Token 必须变化，旧值返回 409 STALE_CASE_RESULT。已完成案例使用新 submission_id 修改时返回 CASE_ALREADY_COMPLETED。

### 12.4 错误合同

所有 JSON 错误统一为 BusinessError：

- code
- 中文 message
- object_type
- 按需出现 object_id
- stage
- next_action
- trace_id

v1 对外错误编号固定为：

| code | HTTP 或案例状态 | 使用条件 |
|---|---:|---|
| INVALID_ZIP | 400 | ZIP 结构、路径、清单、校验值或内容关系不合格 |
| INPUT_CONTRACT_INVALID | 400 | CaseInput、证据来源或案例关系不满足运行合同 |
| ANSWER_LEAKAGE_DETECTED | 400 | 运行包发现答案或答案性质字段 |
| RESOURCE_NOT_FOUND | 404 | 批次、案例或证据不存在；message 指明对象 |
| BATCH_ID_CONFLICT | 409 | 相同 batch_id 对应不同包内容 |
| ACTIVE_BATCH_EXISTS | 409 | 已有首次批量分析正在运行 |
| ACTIVE_CASE_RUN_EXISTS | 409 | 同一案例已有活动运行；幂等命中返回当前视图时不报错 |
| CASE_NOT_RERUNNABLE | 409 | 当前案例状态不允许重跑 |
| CASE_ALREADY_COMPLETED | 409 | 已完成案例收到新的审核或重跑请求 |
| STALE_CASE_RESULT | 409 | review_token 不再对应当前结果 |
| UPLOAD_TOO_LARGE | 413 | ZIP 超过冻结的 `upload.max_zip_bytes` |
| UNSUPPORTED_MEDIA_TYPE | 415 | 上传或证据媒体类型不受支持 |
| REQUEST_VALIDATION_FAILED | 422 | HTTP 字段、联合请求、类型或枚举不合格 |
| ANALYSIS_UNAVAILABLE | 503 | 缺密钥、模型健康检查失败或应用正在正常关闭 |
| INTERNAL_ERROR | 500 | 未预期内部异常；细节只进技术记录 |

案例异步处理错误固定使用 `EVIDENCE_READ_FAILED`、`EVIDENCE_MEDIA_INVALID`、`MODEL_AUTH_FAILED`、`MODEL_TIMEOUT`、`MODEL_RATE_LIMITED`、`MODEL_RESPONSE_INVALID`、`MODEL_ATTEMPTS_EXHAUSTED`、`RESULT_PERSISTENCE_FAILED`、`APP_INTERRUPTED`、`UNEXPECTED_PROCESSING_ERROR`。这些编号通过 `processing_error` 业务化展示，不把供应商状态码、异常类名或内部阶段透传。

HTTP 只使用 200、201、202、400、404、409、413、415、422、503、500。FastAPI 默认 422 和未处理 500 必须转换为同一结构。页面不得看到异常类名、堆栈、密钥、SDK 原始错误、本机路径和供应商响应。

## 13. M4 前端工作台

### 13.1 技术栈

React、TypeScript、Vite、Ant Design、React Router、TanStack Query、Ant Design Form、openapi-typescript、openapi-fetch、Vitest、React Testing Library、MSW 和 Playwright。

本期不引入 Tailwind CSS、Redux、Zustand、GSAP、Motion 或第二套组件库和图标库。

### 13.2 三个页面地址

| 地址 | 责任 |
|---|---|
| / | 工作台入口；没有批次时导入 ZIP，有批次时进入最近批次 |
| /batches/:batchId | 批次摘要、分析进度、案例队列、筛选和开始分析 |
| /batches/:batchId/cases/:caseId | 高价值结论、风险原因、证据、处理建议和人工确认 |

当前批次、当前案例、筛选和分页位置写入 URL。TanStack Query 只保存可失效缓存。localStorage 不保存或覆盖批次、案例、分析和人工确认事实。

### 13.3 用户可见规则

- 页面先回答“谁是高价值客户、为什么有风险、应该怎么做”。
- 导入和开始分析是两个独立动作，同一区域只有一个主按钮。
- 案例详情首屏先显示高价值结论、主要原因和处理建议，再按需展开证据。
- 处理中的内部 Agent 阶段、运行编号、Token、Prompt、Schema、模型日志和 RFM 过程不进入页面。
- 业务状态、介入等级和错误同时使用文字、图标和颜色，不能只靠颜色。
- 已完成案例只读。
- Mock 环境必须明确提示；金额不得推断币种。
- 所有核心点击区域至少 44×44px。
- 1366×768 是主要验收尺寸，1024×768 是最低可用尺寸；页面主体不能水平滚动，案例表格可局部滚动。
- 键盘能够完成上传后的主操作、队列导航、证据展开和人工确认。
- 正文和核心控件达到 WCAG AA。
- 字体、图标和必要资源本地打包，运行时不依赖 CDN。

### 13.4 设计依据与取舍顺序

视觉规范采用两份用户指定依据：本地 `DESIGN-apple.md` 的 SHA-256 为 `83FBC614443A9B3D7569E9956A43E7B8740F9D0F939F58B8154F7A7CEC3002B2`；GitHub `Leonxlnx/taste-skill` 固定参考提交为 `ccbc15639c97057cbfcf32ecebc38ef716e4bb37`。前者是 `version: alpha` 的设计分析，不冒充 Apple 官方规范；后者只读采用一致性、完整状态、表单、响应式和可访问性原则，不采用 AIDA、巨大 Hero、随机版式、GSAP 和营销页结构。

冲突时依次服从：业务信息与操作正确、可访问性和 1024px 可用、本文规则、Apple 视觉参考、taste-skill 通用建议、Ant Design 默认样式。审美不能覆盖证据、错误、不确定性和人工操作。

设计参数固定为：`DESIGN_VARIANCE=3`、`MOTION_INTENSITY=2`、`VISUAL_DENSITY=6`。目标是冷静、可信、克制、有证据感的 B2B 决策工作台，不是营销网站或数据大屏。

### 13.5 视觉令牌

| 类型 | 固定值与规则 |
|---|---|
| 主动作蓝 | `#0066cc`，只用于主按钮、链接和当前选中 |
| 焦点蓝 | `#0071e3`，用于键盘焦点环 |
| 深色表面链接 | `#2997ff`，只用于黑色顶部区域 |
| 文字 | 主文字 `#1d1d1f`；次要文字 `#333333`；非关键禁用文字 `#7a7a7a` |
| 表面 | 页面白 `#ffffff`；页面浅灰 `#f5f5f7`；次级表面 `#fafafc`；分隔线 `#e0e0e0`；顶部栏 `#000000` |
| 状态色 | 成功 `#1f7a3d`、提醒 `#8a4b00`、错误 `#b42318`；必须同时配文字和图标 |
| 字体 | 本地打包 Inter；回退为 `"SF Pro Text"`、system-ui、`"Segoe UI"`、sans-serif；`font-display: swap` |
| 字号 | 页面标题 34px/600/1.2；区块标题 21px/600/1.25；结论正文 17px/400/1.47；表格表单按钮 14px/400 或 600/至少 1.43；辅助信息 12px |
| 间距 | 8px 基础节奏，优先使用 4、8、12、17、24、32、48；1366px 左右 32px，1024px 左右 24px |
| 圆角 | 业务卡片 18px；紧凑控件和证据图片 8px；主按钮和筛选控件可用胶囊形；同类组件保持一致 |
| 层级 | 不使用投影；用白、浅灰、1px 分隔线和留白形成层级 |
| 动效 | 只允许必要按下、展开和状态过渡；按下 `scale(0.98)`，只过渡 transform 和 opacity，120—180ms |

主题通过 Ant Design `ConfigProvider`、集中 CSS 变量和 CSS Modules 实现。主题至少拆为 colors、typography、spacing、radius、motion、z-index 六组；页面组件不得散落十六进制颜色、圆角和间距常量。数字列使用等宽数字。Inter 字体与许可证进入仓库，运行时不请求 Google Fonts 或其他 CDN。

### 13.6 页面结构

- 全局使用 44px 黑色顶部栏，只放产品名和产品级入口；52px 浅灰次导航显示当前批次、业务状态和本页主操作。
- 主内容最大宽度 1440px，使用工作台信息密度，不采用窄营销正文列。
- 导入页左对齐标题；上传区只突出 ZIP、校验、Mock 标记和下一动作。导入成功后主动作从“导入批次”切换为“开始分析”。
- 队列页用一条横向摘要带，不用三个等宽统计卡；表格直接位于白色表面，以分隔线、行距和字重形成层级。
- 详情页首屏依次显示高价值结论、主要原因、介入等级、处理动作和沟通重点；证据按结论关联并按需展开，图片保留原始宽高比。
- 人工确认固定在底部操作区。界面主意图为通过、修改并确认、驳回；“证据不足”作为驳回后必须形成最终人工判断的结构化分支，API 仍使用四种 `outcome`。
- 1024px 下优先收紧次要列和摘要；页面主体不得横向滚动，只有案例表格区域可以局部横向滚动。

### 13.7 组件、状态与禁止做法

- 一个操作区域最多一个蓝色主按钮；主按钮用“导入批次”“开始分析”“提交确认”等短动词并保持单行。
- 加载状态使用与最终内容形状一致的骨架；空状态说明原因和可执行动作；字段、批次和案例错误留在相关内容附近。
- 表单标签位于输入框上方，帮助文字保留，错误文字位于字段下方；不得用 placeholder 代替标签。
- 图标只使用 `@ant-design/icons`，不使用 Emoji 或第二套图标。状态不能只靠颜色表达。
- 禁止营销 Hero、Bento 业务布局、装饰渐变、AI 紫色光晕、玻璃拟态、卡片投影、假截图、假客户 Logo、假实时指标、滚动锁定、视差、轮播、磁性按钮和自动文字入场。
- 不为视觉效果隐藏处理异常、证据冲突、不确定性、证据缺口和人工修改入口。

### 13.8 前端视觉验收

每个页面必须在 `1366×768` 和 `1024×768` 留下浏览器截图并完成操作验证。正文对比度至少 4.5:1，大字至少 3:1；核心点击区域至少 44×44px；键盘可见焦点完整；断网时字体、图标、页面和必要图片正常；加载、空、分析中、待确认、已完成、处理异常和缺密钥状态布局稳定。页面可见文字扫描不得出现 RFM、Agent、Prompt、Token、Schema、运行编号、模型日志或原始 JSON。

## 14. 启动与使用

项目保留四个统一入口：

| 脚本 | 责任 |
|---|---|
| scripts/bootstrap.ps1 | 检查 Python、Node、uv、pnpm，并按锁文件同步依赖 |
| scripts/dev.ps1 | 用同一配置启动 FastAPI 和 Vite 开发环境 |
| scripts/test.ps1 | 运行确定性检查，不调用真实 GLM |
| scripts/start.ps1 | 构建前端、校验配置、取得锁、迁移、恢复并启动本机演示 |

脚本只能使用项目相对路径、PATH 或项目级工具发现逻辑，不能写成员电脑、WindowsApps 别名或 Codex 缓存绝对路径。

固定案例包先运行 `scripts/prepare-demo-data.ps1`；开发联调运行 `scripts/dev.ps1`，它从同一份 TOML 配置读取 FastAPI 与 Vite 端口。真实生产分析除 `ZAI_API_KEY` 外，还要求 `analysis.production_enabled=true`；该开关只能在 M2-10 自动结构门与双人复核完成后的受审查提交中打开，不能用本机 Fake 或普通测试替代。

演示模式由 FastAPI 在同一 127.0.0.1 端口提供 React 静态文件、/api/v1 和证据图片。用户不需要 Docker、Vite 开发服务器或第二个手工终端。

ZAI_API_KEY 只从环境读取，不写入 Git、日志、页面、数据库、配置示例或普通文档。缺少密钥时，HealthView 明确显示分析不可用，开始和重跑返回 503；历史结果仍可查看。

## 15. 验证与验收

### 15.1 确定性自动验收

scripts/test.ps1 至少覆盖：

| 层级 | 必过内容 |
|---|---|
| 合同 | 严格 Pydantic、禁止额外字段、枚举、证据引用、动作目录、模块依赖方向 |
| M1 | 合格和不合格 ZIP、幂等导入、路径安全、九表迁移、短事务、读回、文件流和原子发布 |
| M2 | 三阶段输入隔离、事件顺序、网络重试、一次修复、请求上限、证据不足、技术失败和程序底线 |
| M3 | 状态转换、禁止转换、开始幂等、单案例重跑、当前与历史统计、review_token、人工结果、启动恢复 |
| API | 十个接口、OpenAPI 快照、分页筛选、稳定排序、全部状态码、BusinessError 和字段白名单 |
| M4 | 加载、空、分析中、待确认、完成、异常、缺密钥、表单、刷新返回、1024px 与 1366px |
| E2E | 用测试专用确定性模型替身跑导入、开始、成功、失败、人工确认、重跑、刷新和重启读回 |

测试替身必须经过真实模块边界，不能绕过 ZIP、证据、状态机、数据库或 HTTP。Fake 不进入演示构建，页面没有切换 Fake 的入口。

后端执行 Ruff、Pyright、Pytest、Alembic Schema 和依赖边界检查。前端执行 ESLint、TypeScript、Vitest、React Testing Library、OpenAPI 生成结果检查和 Playwright。

### 15.2 真实 GLM 验收

真实 GLM 验收单独运行，不放入普通确定性测试：

1. 使用官方 SDK 和真实 ZAI_API_KEY 完成健康检查和单案例三阶段冒烟。
2. 选定配置完整运行 demo_batch_v1 与 acceptance_batch_v1，共 15 个案例、45 个阶段；不能跳过、替换或删除失败案例。
3. 所有发布结果必须经过严格合同，不能存在跨案例或不存在的证据、目录外动作、隐藏答案字段或密封答案泄漏。
4. 任何阶段耗尽允许请求后，案例进入可解释的 PROCESSING_ERROR，不能用预写答案或 Fake 补成功。
5. 保存每阶段首次结构通过、修复后通过、失败类别、耗时、Token、实际调用次数、429 和图片贡献记录。
6. 比较 reasoning_effort high 与 max，以及并发 1、2、3；根据真实结果冻结正式参数和内部成本预警线。
7. 5 个密封验收案例由两名验收者检查：关键事实不编造，主要原因有证据，冲突和不确定性表达诚实，介入等级符合程序规则，动作在目录内，整体可作为人工决策初稿。

41/45 首次通过、首例 2 分钟和十例 10 分钟只保留为历史目标，不是本规格的验收阈值。正式阈值只能从真实 PoC 记录中产生。未完成 PoC 前，不能声称模型质量、速度或费用已经达标。

2026-09-11 真实 PoC 已完成参数对照。正式参数选择 `reasoning_effort=high`、案例并发 2、`max_tokens=4096`、完整响应上限 300 秒。最终 run_id `20260911T040909Z` 为 15/15 案例、45/45 阶段通过，首个完整案例约 27 秒，10 个演示案例约 4 分 14 秒；10 个包含图片的案例均产生图片观察且图片证据进入下游判断，8 个案例的行为证据进入下游判断。`max + 并发 2` 只成功 2/15，主要失败为无可校验正文；并发 1 虽全部通过但更慢，并发 3 虽更快但出现一次可恢复连接错误且定向修复更多。自动结构门已经通过，双人业务复核仍为 `PENDING`，因此 `analysis.production_enabled` 继续保持 `false`。

### 15.3 人工演示验收

从一个空的 runtime_data 开始，使用浏览器完成：

1. 导入 demo_batch_v1，看到正确摘要和 Mock 提示，且没有自动调用模型。
2. 明确开始分析，刷新页面后状态和进度继续正确。
3. 打开一个完成分析的案例，看到高价值结论、原因、证据、动作和不确定性。
4. 完成一次直接通过、一次修改后确认、一次证据不足或驳回并给出判断。
5. 重复提交同一 submission_id 不产生第二条记录；旧 review_token 不落库。
6. 对待确认或异常案例重新分析，旧运行历史保留，当前结果切换，批次当前统计更新。
7. 分析中强制终止应用后重启，未完成运行变成可解释的中断错误，不自动调用 GLM，人工可从头重跑。
8. 关闭浏览器再打开，或直接访问案例 URL，结果完整读回。
9. 在 1366×768 与 1024×768 下完成核心操作，键盘可用，断网不丢字体、图标和页面资源。

## 16. 四人并行执行与 37 张 Task

### 16.1 拆分结论

任务总数为 37 张：M1 九张、M2 十张、M3 九张、M4 九张。每张卡适合一个新的 AI 上下文独立执行，声明真实阻塞边，完成后有一个可验证结果。任务全部保存在本文件，不再复制维护 37 份本地任务正文；进入 Git 协作后可以为每张卡建立只引用本节的 Issue。

纯粹按用户功能做纵向切片，会让四个人反复同时修改 M1、M2、M3、M4，增加冲突。这里采用“模块内完整切片 + 三次真实接线”的方式：普通 Task 从本模块输入合同走到输出合同和测试；只有 M3-08、M3-09、M4-09 承担相邻模块或整机接线。

### 16.2 领取、分支与验收规则

1. M3-01 是唯一开工前置。完成后，M1-01、M2-01、M3-02、M4-01 四张卡可同时开始。
2. 依赖项全部完成的 Task 才进入可领取队列。执行者按依赖前沿领取，不按编号机械等待其他模块。
3. 一张 Task 对应一名执行者、一个主模块、一个 `task/<Task-ID>-<简短名称>` 分支和一个 PR。没有远程仓库时先保留本地分支与提交，不虚构 PR。
4. 普通 Task 只改声明目录和对应测试。共享合同变更只允许出现在 M1-01、M2-01、M3-01；其他卡发现合同缺口时停止扩展范围。
5. M1 由 M3 交叉审查，M2 由 M3 交叉审查，M4 由 M3 交叉审查；M3 接入哪个模块，就由哪个模块审查。M3-01、M1-09 的固定验收夹具和最终 E2E 由四人共同审查。

### 16.3 统一自动验收入口

M3-01 建立统一测试入口。每张卡的自动验收命令固定为：

    powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test.ps1 -Task <Task-ID>

合并前再运行所属模块：

    powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test.ps1 -Module <M1|M2|M3|M4>

M3-09 与 M4-09 还必须运行无参数全量确定性测试。M2-10 的真实 GLM 验证使用独立 `live_glm` 标记，不进入普通 PR 门槛。测试优先验证最高稳定边界：合同卡测 Pydantic 和 Protocol，M1/M2 测公开端口，M3 测 HTTP，M4 测用户旅程；不把内部类名和函数拆法写成验收条件。

### 16.4 M1 数据与存储，共 9 张

#### M1-01 冻结数据合同与最小样例

- **类型**：AFK，纯共享合同卡。
- **目标**：把 CaseInput v1、三类 Evidence、ZIP manifest 和 checksums 变成严格可导入合同。
- **输入**：本规格第 5、7.2、8、11 节。
- **输出**：`data.py` 严格 Pydantic 合同、合法与非法最小样例、合同测试。
- **依赖**：M3-01。
- **修改范围**：`backend/app/contracts/data.py`、`tests/contracts/data/`、`tests/fixtures/runtime/contracts/`。
- **禁止事项**：不得加入 case_trigger、行为窗口、币种、答案字段、ORM、FastAPI、SDK 或当前数据不能支持的字段。
- **自动验收**：运行统一命令；额外字段、宽松类型、跨案例证据、缺来源和禁用字段全部被拒绝，合法样例可往返序列化。
- **人工验收**：M2、M3 主责人确认合同足以构造阶段输入和导入流程，没有要求消费者猜字段。

#### M1-02 建立九表 SQLite 与 Alembic

- **类型**：AFK，迁移卡。
- **目标**：实现第 11 节九表、外键、唯一约束、枚举约束和空库升级。
- **输入**：本规格第 10、11 节；M1-01 数据合同；M3-01 状态合同。
- **输出**：SQLAlchemy 模型、Alembic 初始迁移、Schema 快照与约束测试。
- **依赖**：M1-01、M3-01。
- **修改范围**：`backend/app/modules/data/db/`、`backend/alembic/`、`tests/m1/db/`。
- **禁止事项**：不得新增第十张业务表、异步数据库、多进程写入、自动备份、删除或重建已有数据库逻辑。
- **自动验收**：空库升级、重复升级、外键、唯一约束、活动运行约束和九表字段快照全部通过。
- **人工验收**：M3 主责人逐表确认当前投影、首次历史、单案例重跑、模型调用和人工结果没有混写。

#### M1-03 实现 ZIP 暂存与完整校验

- **类型**：AFK。
- **目标**：在不写正式数据库前完成单 ZIP 的路径、安全、Schema、校验值、媒体和答案泄漏检查。
- **输入**：本规格第 5.4—5.6、12.4 节；M1-01。
- **输出**：临时暂存、解压边界、检查报告、失败清理和恶意包夹具。
- **依赖**：M1-01。
- **修改范围**：`backend/app/modules/data/importing/`、`tests/m1/importing/`、ZIP 负向夹具。
- **禁止事项**：不得接受服务器路径、自动修复坏包、清洗原始大数据、发布批次、调用模型或恢复中断临时目录。
- **自动验收**：覆盖路径穿越、绝对路径、符号链接、重复 ID、错哈希、超 20 案例、非法媒体、答案字段和未脱敏内容。
- **人工验收**：M3 主责人确认每类拒绝结果都有稳定编号和可操作说明，不含本机路径与客户正文。

#### M1-04 实现 BatchImportGateway 原子导入

- **类型**：AFK。
- **目标**：把通过校验的包原子发布为 PENDING_ANALYSIS 批次，并实现包哈希幂等和批次冲突。
- **输入**：本规格第 5.4、8、11 节；M1-02、M1-03。
- **输出**：BatchImportGateway SQLite 实现、正式批次文件、导入摘要和回滚测试。
- **依赖**：M1-02、M1-03。
- **修改范围**：`backend/app/modules/data/importing/`、`backend/app/modules/data/repositories/`、`tests/m1/import_gateway/`。
- **禁止事项**：不得在导入成功后自动开始分析，不得留下半批次，不得把不同内容的同一 batch_id 当作幂等。
- **自动验收**：新包创建一次、同包返回原批次、同 ID 异内容冲突；任一文件或事务故障后正式目录和九表均无半成品。
- **人工验收**：M3 主责人只通过公开网关完成导入并读到文件名、案例数、证据数和 Mock 标记。

#### M1-05 实现 CaseQueryGateway 与当前投影

- **类型**：AFK。
- **目标**：提供批次列表、批次详情、案例队列、案例详情和 CaseInput 查询所需的稳定业务投影。
- **输入**：本规格第 8、10.3、11、12.2 节；M1-02、M1-04。
- **输出**：CaseQueryGateway SQLite 实现、分页筛选、固定排序、当前系统或人工结果投影。
- **依赖**：M1-02、M1-04。
- **修改范围**：`backend/app/modules/data/queries/`、`backend/app/modules/data/repositories/`、`tests/m1/query_gateway/`。
- **禁止事项**：不得返回 ORM、Session、内部整数 ID 或运行编号，不得从任意 JSON 临时排序，不得形成第三套前端统计。
- **自动验收**：分页边界、批次倒序、案例业务排序、筛选、人工结果优先和当前与首次历史分离全部通过。
- **人工验收**：M3 主责人确认返回对象可直接映射业务 DTO，不需要访问 M1 内部实现。

#### M1-06 实现 EvidenceGateway 安全文件流

- **类型**：AFK。
- **目标**：按 batch_id、case_id、evidence_id 提供归属正确的图片流和媒体类型。
- **输入**：本规格第 5.6、8、11.3、12.1 节；M1-03、M1-04。
- **输出**：EvidenceGateway 实现、受控文件名、媒体响应元数据和安全测试。
- **依赖**：M1-03、M1-04。
- **修改范围**：`backend/app/modules/data/evidence/`、`tests/m1/evidence_gateway/`。
- **禁止事项**：不得返回绝对路径、开放目录、接受路径参数、跨案例读取、把图片存入 SQLite BLOB 或转换 GIF 原文件。
- **自动验收**：合法图片可读；跨批次、跨案例、不存在证据、路径穿越、错误媒体和文件替换全部拒绝。
- **人工验收**：M3 主责人通过公开端口取得图片流，无法从返回内容推断本机目录。

#### M1-07 实现 RunStore、历史追加与原子发布

- **类型**：AFK。
- **目标**：保存批次运行、案例运行、模型尝试、阶段结果、失败和完整结果发布，并提供中断恢复所需原子操作。
- **输入**：本规格第 8—11 节；M1-02、M2-01、M3-01。
- **输出**：RunStore SQLite 实现、当前指针切换、批次当前计数、首次历史和恢复原语。
- **依赖**：M1-02、M2-01、M3-01。
- **修改范围**：`backend/app/modules/data/run_store/`、`tests/m1/run_store/`。
- **禁止事项**：不得决定业务状态转换、等待 GLM 时持有事务、覆盖旧运行、发布半个决策包或让人工重跑改写 batch_runs。
- **自动验收**：事件追加、活动唯一性、写入回滚、成功发布、失败记录、中断标记、当前计数和历史不变性全部通过。
- **人工验收**：M3 主责人确认每个编排决定都能用一个短事务命令完成，M3 不需要接触 Session。

#### M1-08 实现 ReviewStore 与 M1 模块验收

- **类型**：AFK。
- **目标**：保存四种人工确认，保证 submission_id 幂等、当前运行校验、已完成只读和系统原结果可追溯。
- **输入**：本规格第 8、10、11、12.3 节；M1-05、M1-07。
- **输出**：ReviewStore SQLite 实现、Fake 与真实端口共用合同测试、M1 模块验收结果。
- **依赖**：M1-05、M1-07。
- **修改范围**：`backend/app/modules/data/review_store/`、`backend/app/modules/data/fakes/`、`tests/m1/review_store/`、`tests/contracts/data_ports/`。
- **禁止事项**：不得复制系统决策包、接受过期 Token、允许第二份正式审核、无痕修改已完成案例或让 Fake 跳过真实合同。
- **自动验收**：四种合法结果、非法字段、重复提交、过期运行、并发提交、回滚和 Fake/SQLite 一致性全部通过。
- **人工验收**：M3 主责人用 Fake 与 SQLite 分别运行同一调用，确认返回类型、错误编号和最终投影一致。

#### M1-09 生成固定数据快照、案例包与密封验收集

- **类型**：HITL，确定性数据处理加四人共同业务核验。
- **目标**：以现有清洗后主表为主、同源原始表为核验补充，生成可复算的 `mock_dataset_v1`、10 案例演示 ZIP、5 案例验收 ZIP和物理分离的密封参考结果。
- **输入**：本规格第 5、7.2、15.2 节；M1-01；逻辑源目录 `source_data/ecommercedata-main/`。
- **输出**：可重复运行的数据组包程序；`demo_batch_v1.zip`；`acceptance_batch_v1.zip`；密封参考 JSON；一个普通客户测试对照；独立技术故障夹具；源文件哈希、固定映射、RFM 边界、案例覆盖和脱敏检查报告。
- **依赖**：M1-01。
- **修改范围**：`tools/data_preparation/`、`tests/fixtures/batches/`、`tests/fixtures/sealed/`、`tests/fixtures/failures/`、`docs/data/`；不得修改产品运行模块。
- **禁止事项**：不得寻找新数据、重新随机映射、强行跨源认定真实客户、把 CSV 行直接当案例、沿用旧绝对 RFM 阈值、把密封答案写入运行 ZIP、Prompt 或产品目录、用虚构时间或币种补字段。
- **自动验收**：连续运行两次得到相同清单和内容哈希；当前 RFM 复算得到 96,095 名客户、三个已记录分位边界和 15,208 名高价值客户；两包案例互不重叠且均通过 M1-01 Schema；答案泄漏扫描为零；图片引用全部存在；运行 ZIP 不包含源大表或密封文件。
- **人工验收**：四名成员逐条检查 15 个案例的来源、Mock 标记、语义不冲突和脱敏；5 个验收案例共同覆盖三档介入、证据冲突、模态缺失或证据不足，其中至少一个图文支持、一个图文冲突和一个行为贡献案例。检查结果只写密封参考，不写入运行输入。

### 16.5 M2 AI 分析引擎，共 10 张

#### M2-01 冻结分析合同、事件与动作目录

- **类型**：AFK，纯共享合同卡。
- **目标**：实现 PerceptionResult、AttributionResult、DecisionPackage、AnalysisRequest、AnalysisOutcome、AnalysisEventSink 和 action_catalog.v1。
- **输入**：本规格第 5.6、7、9 节。
- **输出**：`analysis.py` 严格合同、受控枚举、动作目录和合同样例测试。
- **依赖**：M3-01。
- **修改范围**：`backend/app/contracts/analysis.py`、`config/action_catalog.v1.json`、`tests/contracts/analysis/`。
- **禁止事项**：不得导入数据库、FastAPI、智谱 SDK 或模块实现，不得增加概率、Embedding、坐标、补偿金额和真实执行状态。
- **自动验收**：严格类型、字段上限、六个动作、六个原因加非原因兜底、事件联合类型和禁止额外字段全部通过。
- **人工验收**：M1、M3 主责人确认事件能持久化、结果能编排，消费者不需要读取供应商响应。

#### M2-02 实现 Prompt、Schema 注入与版本指纹

- **类型**：AFK。
- **目标**：让三个 Prompt 只描述各自职责，并从 Pydantic 生成唯一 JSON Schema。
- **输入**：本规格第 7、9.2、9.4 节；M2-01。
- **输出**：三个 v1 Prompt、加载器、Schema 注入、版本与 SHA-256 清单。
- **依赖**：M2-01。
- **修改范围**：`backend/app/modules/analysis/prompts/`、`tests/m2/prompts/`。
- **禁止事项**：不得复制维护第二份字段表，不得写 API Key、固定案例答案、密封答案、其他案例或越权上下文。
- **自动验收**：Prompt 快照、Schema 同源、哈希变化、禁用词与密封答案扫描、缺文件失败全部通过。
- **人工验收**：业务成员逐份检查职责、证据边界、不确定性和输出要求可读，三份 Prompt 不互相代做职责。

#### M2-03 实现唯一 GlmClient

- **类型**：AFK。
- **目标**：通过官方 zai-sdk 建立唯一真实模型边界，并提供同合同测试客户端。
- **输入**：本规格第 3.2、9.3、14 节；M2-01、M3-02。
- **输出**：GlmClient、测试客户端、请求清单、超时与供应商错误分类。
- **依赖**：M2-01、M3-02。
- **修改范围**：`backend/app/modules/analysis/client/`、`tests/m2/client/`。
- **禁止事项**：不得读取数据库、处理状态机、开启 SDK 自动重试、日志记录密钥或让三个阶段各自调用 SDK。
- **自动验收**：文本和图片请求、JSON 输出、参数读取、超时、401/403/429/5xx 分类、敏感信息扫描和测试客户端一致性通过。
- **人工验收**：M3 主责人检查调用返回只含编排需要的数据与稳定错误，不泄露 SDK 对象。

#### M2-04 实现严格结果与证据校验器

- **类型**：AFK。
- **目标**：集中完成 JSON、Pydantic、case_id、evidence_id、跨阶段引用、动作目录和最低介入规则校验。
- **输入**：本规格第 5.6、7、9.2、9.4 节；M1-01、M2-01。
- **输出**：阶段校验器、可定向修复的结构化错误和参数化负向测试。
- **依赖**：M1-01、M2-01。
- **修改范围**：`backend/app/modules/analysis/validation/`、`tests/m2/validation/`。
- **禁止事项**：不得调用模型、修改原始证据、用宽松转换放行、自动补字段或因主观质量偏好判定失败。
- **自动验收**：多余字段、错误类型、跨案例证据、越权证据、目录外动作、数量超限和低于程序底线全部覆盖。
- **人工验收**：M3 主责人确认错误能稳定区分可修复结构问题和不可重试输入问题。

#### M2-05 实现感知阶段

- **类型**：AFK。
- **目标**：从当前案例获准文本、图片和订单事实生成严格 PerceptionResult。
- **输入**：本规格第 7.1、9.2 节；M1-01、M2-02、M2-03、M2-04。
- **输出**：感知输入构造器、阶段执行器、图片观察和事件情绪测试。
- **依赖**：M1-01、M2-02、M2-03、M2-04。
- **修改范围**：`backend/app/modules/analysis/perception/`、`tests/m2/perception/`。
- **禁止事项**：不得传入高价值结论、RFM、风险答案、动作目录、其他案例或密封答案；模糊图不得从文本反推图片事实。
- **自动验收**：请求清单最小化、每图一条观察、unknown、图文支持与冲突、客户情绪证据和禁止字段测试通过。
- **人工验收**：业务成员检查固定样例事件与图片观察只陈述证据，不提前生成原因和策略。

#### M2-06 实现归因阶段

- **类型**：AFK。
- **目标**：基于 PerceptionResult 和获准证据生成可反驳的风险原因假设。
- **输入**：本规格第 7.1、7.2、9.2 节；M2-02、M2-03、M2-04。
- **输出**：归因输入构造器、阶段执行器、主要原因与最多一个备选原因测试。
- **依赖**：M2-02、M2-03、M2-04。
- **修改范围**：`backend/app/modules/analysis/attribution/`、`tests/m2/attribution/`。
- **禁止事项**：不得重复发送原图和完整对话，不得读取高价值结论、RFM、动作目录或把原因写成已证明因果事实。
- **自动验收**：六原因枚举、证据不足兜底、支持与反证、备选原因条件、输入越权和跨阶段引用测试通过。
- **人工验收**：业务成员检查主要原因有证据，反证和未知没有被隐藏，OTHER 与 INSUFFICIENT_EVIDENCE 没有混用。

#### M2-07 实现策略阶段与程序底线

- **类型**：AFK。
- **目标**：从两个上游结果、高价值结论和动作目录生成受约束 DecisionPackage。
- **输入**：本规格第 7.3、7.4、9.2 节；M2-01、M2-02、M2-03、M2-04。
- **输出**：策略输入构造器、阶段执行器、程序最低介入调整和动作测试。
- **依赖**：M2-01、M2-02、M2-03、M2-04。
- **修改范围**：`backend/app/modules/analysis/strategy/`、`tests/m2/strategy/`。
- **禁止事项**：不得读取原图、完整原始对话、RFM 过程；不得生成目录外动作、金额承诺、退款完成或自动执行业务动作。
- **自动验收**：三档等级、严重问题底线、最多三动作和三沟通点、证据引用、等级调整不增加模型请求全部通过。
- **人工验收**：业务成员检查固定样例建议可作为人工初稿，且高价值身份没有单独触发必须介入。

#### M2-08 实现 AnalysisEngine、重试修复与事件序列

- **类型**：AFK。
- **目标**：把三个阶段顺序组成唯一阻塞入口，执行有界重试、一次修复、阶段停止和类型化事件输出。
- **输入**：本规格第 9、10.6 节；M2-05、M2-06、M2-07。
- **输出**：AnalysisEngine、重试策略、修复请求、关闭检查、成功与失败 AnalysisOutcome。
- **依赖**：M2-05、M2-06、M2-07。
- **修改范围**：`backend/app/modules/analysis/engine/`、`tests/m2/engine/`。
- **禁止事项**：不得创建线程池、读写数据库、启动服务、并行同案例阶段、失败后继续后续阶段或超过每阶段四次请求。
- **自动验收**：合法事件顺序、网络重试、不可重试错误、一次修复、修复网络失败、请求上限、事件保存失败和阶段边界关闭通过。
- **人工验收**：M3 主责人只用 `analyze_case` 与事件出口完成一次成功和一次失败编排，无需读取 M2 内部类。

#### M2-09 完成 M2 确定性模块验收

- **类型**：AFK。
- **目标**：用测试客户端跑通三阶段成功、证据不足和全部规定技术失败，形成可供 M3 接线的稳定模块。
- **输入**：本规格第 9、15.1 节；M2-08。
- **输出**：M2 模块测试集、请求清单快照、事件快照和 Fake/真实客户端合同一致性结果。
- **依赖**：M2-08。
- **修改范围**：`tests/m2/`、`tests/contracts/analysis_engine/`；只允许修复 M2 内部缺陷。
- **禁止事项**：不得调用真实 GLM、放宽合同、使用密封答案、绕过图片或只测试成功路径。
- **自动验收**：统一 Task 命令和 `-Module M2` 均通过，且模型网络调用计数为零。
- **人工验收**：M3 主责人依据合同样例复现成功、证据不足和超时三个结果，确认可以开始 M2—M3 接线。

#### M2-10 运行真实 GLM 冒烟与 15 案例 PoC

- **类型**：HITL，需要真实密钥、模型费用和两名人工验收者。
- **目标**：用正式接线完整运行 15 个固定案例、45 个阶段，并据实冻结模型参数和并发。
- **输入**：本规格第 15.2 节；M1-09、M2-09、M3-09；环境变量 `ZAI_API_KEY`。
- **输出**：真实冒烟结果、PoC 报告、summary.json、case-results.json、失败记录和正式参数结论。
- **依赖**：M1-09、M2-09、M3-09。
- **修改范围**：`tests/live_glm/`、`artifacts/poc/`、`docs/poc/`、经 PoC 证明需要调整的 M2 内部配置。
- **禁止事项**：不得把密封答案送入模型、删除或替换失败案例、改答案迎合模型、用 Fake 补成功，或把 41/45、2 分钟、10 分钟当预设硬门槛。
- **自动验收**：运行 `uv run pytest -m live_glm tests/live_glm`；45 个阶段均有调用或明确失败记录，所有发布结果严格有效，产物可互相核对。
- **人工验收**：两名验收者独立检查 5 个密封案例并记录结论；团队依据耗时、Token、429 和质量记录冻结 reasoning_effort、超时与并发。

### 16.6 M3 业务服务与 API，共 9 张

#### M3-01 初始化单仓库、共享状态合同与质量入口

- **类型**：AFK，四模块共同前置卡。
- **目标**：建立可分支协作的单仓库、冻结目录、共享状态错误合同和统一测试入口。
- **输入**：本规格第 3、6、7.2、14—16 节。
- **输出**：Git 仓库、模块目录、依赖锁定基础、`.gitignore`、`states.py`、四个 PowerShell 入口和 Task/Module 测试分发器。
- **依赖**：无。
- **修改范围**：仓库根配置、`backend/app/contracts/states.py`、空模块目录、`config/`、`scripts/`、测试入口骨架。
- **禁止事项**：不得写产品业务逻辑、连接远程仓库或虚构 PR，不得建立第五个业务模块、通用业务 `utils`，不得把密钥和 runtime_data 纳入 Git。
- **自动验收**：运行 M3-01 Task 命令；目录边界、锁文件、脚本参数、Git 忽略、状态枚举和反向依赖负向夹具通过。
- **人工验收**：四名成员共同确认目录归属、分支命名、交叉审查关系和本机启动入口，不存在无人负责的共享业务目录。

#### M3-02 实现配置、应用工厂与 HealthView

- **类型**：AFK。
- **目标**：集中读取严格配置，以显式依赖注入创建 FastAPI，并在缺密钥时保留历史只读能力。
- **输入**：本规格第 3.2、6、12.2、14 节；M3-01。
- **输出**：pydantic-settings 配置、应用工厂、生命周期骨架、HealthView 和 Fake 注入测试。
- **依赖**：M3-01。
- **修改范围**：`backend/app/modules/application/config/`、`backend/app/modules/application/app_factory/`、`tests/m3/config/`。
- **禁止事项**：不得使用可变全局装配、缺密钥自动切 Fake、监听非回环地址、把密钥写入日志或业务响应。
- **自动验收**：默认与本机覆盖、非法类型、端口冲突、缺密钥、Fake 仅测试注入和 HealthView 白名单测试通过。
- **人工验收**：M1、M2 主责人确认真实与 Fake 都通过显式参数装配，应用工厂不导入模块内部实现。

#### M3-03 实现业务 DTO、BusinessError 与 OpenAPI 快照

- **类型**：AFK，M3—M4 合同卡。
- **目标**：把十个接口、最小业务 DTO、四种审核请求和统一错误结构变成可生成的 OpenAPI 真源。
- **输入**：本规格第 7.2、12 节；M1-01、M2-01、M3-02。
- **输出**：严格请求响应模型、十个路由签名、错误映射边界、OpenAPI 快照。
- **依赖**：M1-01、M2-01、M3-02。
- **修改范围**：`backend/app/modules/application/api/contracts/`、`backend/app/modules/application/api/router.py`、`tests/m3/openapi/`。
- **禁止事项**：不得实现通用 CRUD、暴露运行编号或 ORM、增加第十一个接口、返回 FastAPI 默认 detail 或把供应商错误透传。
- **自动验收**：十个方法路径、成功码、允许状态码、字段白名单、四种请求联合类型、review_options 和 OpenAPI 快照通过。
- **人工验收**：M4 主责人确认三个页面所需字段完整，技术字段和无意义 null 不进入合同。

#### M3-04 实现导入、查询、证据与健康接口

- **类型**：AFK。
- **目标**：使用 Fake M1 跑通上传、批次列表详情、案例队列详情、证据内容和健康读取。
- **输入**：本规格第 8、12 节；M3-03；M1-01 的端口合同。
- **输出**：七个读取与导入接口、分页筛选、文件流响应和稳定错误映射。
- **依赖**：M1-01、M3-03。
- **修改范围**：`backend/app/modules/application/api/`、`backend/app/modules/application/services/query/`、`tests/m3/api_read_import/`。
- **禁止事项**：不得解析 ZIP 内部、直接读 SQLite、返回本机路径、在前端排序或让 Fake 绕过接口合同。
- **自动验收**：新导入 201、重复 200、列表详情、筛选分页、证据归属、413/415/422/500 和响应白名单通过。
- **人工验收**：M1 主责人确认 M3 只调用五个公开端口，不依赖 M1 实现类和 ORM。

#### M3-05 实现 RunService、状态机与批次开始

- **类型**：AFK。
- **目标**：用 Fake M1 与 Fake M2 完成批次开始、单一执行器、有界案例并发、阶段事件保存和完整发布决定。
- **输入**：本规格第 9、10、12.1 节；M2-01、M3-03。
- **输出**：RunService、案例状态机、ThreadPoolExecutor 生命周期、POST batch runs 接口和事件处理。
- **依赖**：M2-01、M3-03。
- **修改范围**：`backend/app/modules/application/run_service/`、批次开始路由、`tests/m3/run_service/`。
- **禁止事项**：不得直接提交 Session、创建多个线程池、在请求内等待 GLM、暴露内部阶段、自动开始第二批或发布半成品。
- **自动验收**：开始返回 202、重复开始幂等、一个活动批次、每案例一个活动运行、单例失败隔离、事件顺序和完整发布门槛通过。
- **人工验收**：M1、M2 主责人确认状态决定归 M3，数据原子写入归 M1，分析职责归 M2。

#### M3-06 实现单案例重跑与当前投影

- **类型**：AFK。
- **目标**：让待确认或异常案例从头重跑，保留旧历史并正确更新 batches 当前投影。
- **输入**：本规格第 10.2—10.4、12.1 节；M3-05。
- **输出**：POST reruns 接口、重跑幂等、允许与禁止转换、当前和首次历史协调逻辑。
- **依赖**：M3-05。
- **修改范围**：`backend/app/modules/application/run_service/`、重跑路由、`tests/m3/rerun/`。
- **禁止事项**：不得重跑 PENDING_ANALYSIS 或 COMPLETED，不得改写 batch_runs，不得继续旧阶段或返回 case_run_id。
- **自动验收**：合法 202、并发重跑冲突、旧历史保留、成功与失败计数变化、首次历史不变和旧结果不再可审核通过。
- **人工验收**：M1 主责人核对一次成功和一次失败重跑的数据库关系与页面当前统计一致。

#### M3-07 实现人工确认、审核 Token 与幂等

- **类型**：AFK。
- **目标**：完成四种人工确认业务校验、review_token 并发保护、submission_id 幂等和已完成只读。
- **输入**：本规格第 7.2、10.2、12.2—12.4 节；M3-03、M3-06。
- **输出**：POST reviews 接口、Token 生成验证、四种命令处理和当前人工投影。
- **依赖**：M3-03、M3-06。
- **修改范围**：`backend/app/modules/application/review/`、审核路由、`tests/m3/review/`。
- **禁止事项**：不得把 Token 当登录凭证、允许目录外动作、接受旧结果、让 APPROVED 夹带结果或让证据不足填写虚假原因。
- **自动验收**：201/200 幂等、四种合法请求、禁用字段、旧 Token 409、已完成冲突、并发提交和 review_options 一致性通过。
- **人工验收**：M4 主责人确认表单可从 CaseDetailView 完成，不需要新接口或手写枚举。

#### M3-08 完成 M1—M3 接线、启动恢复与正常关闭

- **类型**：AFK，第一张真实接线卡。
- **目标**：把 Fake M1 替换为真实 SQLite 端口，跑通导入、读取、运行记录、审核、启动恢复和 Ctrl+C 收敛。
- **输入**：本规格第 8、10—14 节；M1-08、M3-04—M3-07。
- **输出**：真实 M1 装配、恢复检查、运行目录锁、迁移启动、正常关闭和 M1—M3 集成记录。
- **依赖**：M1-08、M3-04、M3-05、M3-06、M3-07。
- **修改范围**：M3 装配与生命周期适配层、`scripts/start.ps1`、`tests/integration/m1_m3/`；不得改 M1 内部实现。
- **禁止事项**：不得让 M3 操作 ORM、自动备份、自动开浏览器、增加 stop.ps1、自动续跑或因接线修改调用方业务合同。
- **自动验收**：真实 ZIP 导入读回、状态写入、审核、双实例锁、迁移失败、三阶段中断恢复零模型调用和 Ctrl+C 阶段边界测试通过。
- **人工验收**：M1 主责人审查接线范围；从项目根目录外启动后仍只产生一套运行数据，并能手工打开历史结果。

#### M3-09 完成 M2—M3 接线与后端确定性验收

- **类型**：AFK，第二张真实接线卡。
- **目标**：把 Fake M2 替换为真实 AnalysisEngine 加测试客户端，跑通真实合同下的完整后端流程。
- **输入**：本规格第 9—15.1 节；M2-09、M3-08。
- **输出**：真实 M2 装配、事件持久化、完整发布、技术失败映射、最终 OpenAPI 与后端 E2E 记录。
- **依赖**：M2-09、M3-08。
- **修改范围**：M3 的 M2 适配与装配层、`tests/integration/m2_m3/`、`tests/e2e/backend/`；不得改 M2 内部实现。
- **禁止事项**：不得调用真实 GLM、绕过 GlmClient 测试边界、放宽合同、在 GLM 等待时持有事务或把技术异常暴露给 API。
- **自动验收**：运行 M3-09 Task 命令、`-Module M3` 和无参数全量测试；导入到审核、失败、中断、重跑和刷新读回全部确定性通过，网络模型调用为零。
- **人工验收**：M2 主责人审查接线；团队确认后端已具备真实 GLM PoC 前提，不需要改 M1、M2 合同。

### 16.7 M4 前端工作台，共 9 张

#### M4-01 初始化前端、路由骨架与视觉令牌

- **类型**：AFK。
- **目标**：建立 React 单页应用、三个固定路由、集中主题、布局骨架和本地资源边界。
- **输入**：本规格第 13—15 节；M3-01。
- **输出**：Vite/TypeScript 前端、路由壳、Ant Design ConfigProvider、CSS 变量、错误边界和基础测试。
- **依赖**：M3-01。
- **修改范围**：`frontend/` 内构建、路由、主题、布局和对应测试。
- **禁止事项**：不得加入第二套组件库、Tailwind、Redux、Zustand、GSAP、Motion、CDN、营销 Hero 或业务假数据。
- **自动验收**：构建、类型、Lint、路由、主题令牌、依赖白名单、无外部资源和三个页面壳测试通过。
- **人工验收**：业务成员在 1366×768 与 1024×768 检查基础层级冷静、可信、无组件库默认皮肤。

#### M4-02 生成 OpenAPI 客户端与 MSW 合同场景

- **类型**：AFK，前后端合同卡。
- **目标**：从 M3 OpenAPI 生成唯一 TypeScript 类型和请求客户端，并建立完整 MSW 状态样例。
- **输入**：本规格第 12、13 节；M3-03、M4-01。
- **输出**：生成类型、openapi-fetch 客户端、集中错误层、MSW handlers 和合同差异检查。
- **依赖**：M3-03、M4-01。
- **修改范围**：`frontend/src/api/`、`frontend/src/mocks/`、生成文件、`frontend/tests/contracts/`。
- **禁止事项**：不得手写重复 DTO、改写生成文件、解析 ORM/SDK 响应、复制后端枚举或用 `any` 绕过合同。
- **自动验收**：重新生成无差异、旧生成物可被检查发现、十接口类型、BusinessError 和各业务状态的 MSW 场景通过。
- **人工验收**：M3 主责人确认前端请求只使用公开业务字段，合同变化能在合并前使检查失败。

#### M4-03 实现工作台入口与两步导入

- **类型**：AFK。
- **目标**：完成无批次上传、有批次进入最近批次、导入摘要和显式开始前的静止状态。
- **输入**：本规格第 4、5.4、12、13 节；M4-02。
- **输出**：根页面、ZIP 选择与上传、导入摘要、历史批次入口和加载空异常状态。
- **依赖**：M4-02。
- **修改范围**：`frontend/src/pages/workspace/`、相关组件与测试。
- **禁止事项**：不得上传后自动分析、支持服务器路径或多文件、只靠浏览器判定合格、显示本机路径或制造真实客户文案。
- **自动验收**：新导入、重复导入、非法扩展名、空文件、413/415/422、Mock 提示和导入后零开始请求的组件与 MSW 测试通过。
- **人工验收**：业务成员能在一个区域完成导入并清楚看见文件名、案例数、证据数、校验结论和下一主动作。

#### M4-04 实现批次摘要、开始分析与案例队列

- **类型**：AFK。
- **目标**：展示批次当前状态、进度、错误数和按业务优先级排列的案例，并触发一次批量开始。
- **输入**：本规格第 10.3、12.1—12.2、13 节；M4-02。
- **输出**：批次页面、开始按钮、队列表格、状态与介入等级呈现、空与异常状态。
- **依赖**：M4-02。
- **修改范围**：`frontend/src/pages/batch/`、队列组件与测试。
- **禁止事项**：不得显示 Agent 阶段、运行编号、估算等待时间、RFM 过程或用前端重排改变后端顺序。
- **自动验收**：四种批次状态、五种案例状态、开始 202、重复点击保护、部分失败、无密钥禁用和文字图标颜色三重表达通过。
- **人工验收**：业务成员在首屏能判断分析是否结束、谁应先处理、哪些案例异常，不需要理解技术状态。

#### M4-05 实现 URL 状态、筛选分页与有界轮询

- **类型**：AFK。
- **目标**：让批次、案例、筛选和分页位置可刷新恢复，活动批次按唯一节奏轮询。
- **输入**：本规格第 12.1、13.2—13.3 节；M4-04。
- **输出**：URL 参数、TanStack Query 键、2 秒轮询、后台暂停、终态停止和精确失效策略。
- **依赖**：M4-04。
- **修改范围**：`frontend/src/routing/`、`frontend/src/queries/`、批次页面相关测试。
- **禁止事项**：不得用 localStorage 保存业务事实、建立多个组件计时器、轮询终态、添加任意 sort_by 或客户端全量过滤。
- **自动验收**：刷新、返回、直接地址、默认和边界分页、筛选、前后台切换、终态停止和重复挂载无重复请求通过。
- **人工验收**：业务成员切换案例和筛选后刷新，仍回到同一业务位置且结果来自服务端。

#### M4-06 实现案例详情与证据查看

- **类型**：AFK。
- **目标**：按结论优先顺序展示高价值、风险原因、介入等级、动作、沟通重点、证据、冲突和不确定性。
- **输入**：本规格第 12.2、13.2—13.3 节；M4-02。
- **输出**：案例详情页、证据折叠、图片加载、Mock 与币种说明、加载和失败状态。
- **依赖**：M4-02。
- **修改范围**：`frontend/src/pages/case-detail/` 的只读结果与证据组件、相关测试。
- **禁止事项**：不得按感知、归因、策略内部阶段分区，不得显示 evidence_id、Token、Prompt、Schema、绝对路径或未引用证据。
- **自动验收**：完整结果、证据不足、图文冲突、可选图片缺失、图片读取失败、人工结果优先和技术字段扫描通过。
- **人工验收**：业务成员首屏先看懂结论和建议，按需展开证据后能区分事实、推断、冲突和缺口。

#### M4-07 实现人工确认、重跑与只读状态

- **类型**：AFK。
- **目标**：完成四种严格人工确认、待确认或异常重跑、旧结果冲突提示和已完成只读。
- **输入**：本规格第 10.2、12.2—12.4、13.3 节；M3-07、M4-06。
- **输出**：审核表单、review_options 映射、submission_id 重试、review_token 隐藏提交、重跑和错误提示。
- **依赖**：M3-07、M4-06。
- **修改范围**：`frontend/src/pages/case-detail/` 的操作组件、表单与测试。
- **禁止事项**：不得展示 Token、手写动作和原因枚举、允许修改无原因、驳回无判断、证据不足填确定原因或已完成重跑。
- **自动验收**：四种合法表单、禁用字段、目录外动作、重复提交、旧 Token 409、重跑刷新、已完成只读和键盘操作通过。
- **人工验收**：业务成员分别完成通过、修改后确认、驳回并给判断、证据不足，页面结果与输入含义一致。

#### M4-08 完成视觉、可访问性、离线与 MSW E2E

- **类型**：AFK 后接人工截图审查。
- **目标**：把三个页面的全部状态收敛到统一视觉，并在两种桌面尺寸、键盘和断网条件下完成确定性前端旅程。
- **输入**：本规格第 13、15.1、15.3 节；M4-03—M4-07。
- **输出**：响应式细节、焦点与对比度、离线资源检查、组件状态矩阵和 MSW Playwright 报告。
- **依赖**：M4-03、M4-04、M4-05、M4-06、M4-07。
- **修改范围**：`frontend/` 内视觉与可访问性实现、`frontend/tests/e2e-msw/`。
- **禁止事项**：不得增加手机端、第二主题、装饰性数据、仅颜色状态、外部字体图标或为了截图写死结果。
- **自动验收**：1366×768、1024×768、键盘、44×44px、WCAG AA、主体无横向滚动、断网和完整 MSW 旅程通过。
- **人工验收**：业务成员逐页截图审查信息层级、长文案、异常、只读和 Mock 提示，确认不是营销页或默认组件皮肤。

#### M4-09 完成 M4—M3 接线、全量 E2E 与人工演示

- **类型**：HITL，第三张真实接线卡和最终产品验收卡。
- **目标**：替换 MSW 为真实 M3，在单机真实持久化和真实 GLM 结果上完成完整用户闭环。
- **输入**：本规格第 15.3 节；M2-10、M3-09、M4-08。
- **输出**：真实 API 装配、Playwright 全量报告、启动与重启证据、人工演示记录和可交付构建。
- **依赖**：M2-10、M3-09、M4-08。
- **修改范围**：M4 API 装配层、`tests/e2e/`、必要的 M3 静态文件提供适配；不得修改 M1、M2 内部实现。
- **禁止事项**：不得保留 MSW 或 Fake 生产开关、修改合同迎合页面、跳过失败案例、用预写结果替代 GLM 或新增本期外功能。
- **自动验收**：运行 M4-09 Task 命令、`-Module M4` 和无参数全量测试；导入、开始、队列、详情、审核、重跑、刷新、重启和中断恢复全部通过。
- **人工验收**：从空 runtime_data 用浏览器完成第 15.3 节九步，在两种尺寸和断网环境复核；四名成员共同签字确认。

### 16.8 依赖前沿与完成顺序

| 阶段 | 可执行 Task | 完成标志 |
|---|---|---|
| 开工前置 | M3-01 | 仓库、目录、状态合同、测试入口可用 |
| 第一并行前沿 | M1-01、M2-01、M3-02、M4-01 | 四名成员各自进入主模块 |
| 合同与替身开发 | 各模块依赖已满足的普通 Task | 每块可在替身边界独立验收 |
| 固定数据门 | M1-09 | 两个运行 ZIP、密封参考、RFM 和来源报告通过共同审查 |
| 第一接线 | M3-08 | M1—M3 真实导入、存储、恢复通过 |
| 第二接线 | M3-09 | M2—M3 使用测试客户端的确定性后端通过 |
| 真实模型门 | M2-10 | 15 案例 PoC 和两人质量检查完成 |
| 第三接线 | M4-09 | M4—M3、全量 E2E 和人工演示完成 |

任何卡发现会改变 MVP 范围、模型费用上限、数据可行性、用户可见结果、十个接口或验收含义的冲突，停止该卡并升级为合同变更。端口锁、缓存、内部类名、启动器内部步骤等局部问题由卡内直接选择最小实现，不新开产品讨论。

## 17. 被删除或降级的设计

以下内容不作为 MVP 必做项：

- Claude Code Agent Teams 产品运行时、Streamlit 和任何第三方 Agent 编排框架。
- 自动浏览器打开、NoBrowser 参数和 stop.ps1 实例控制协议。
- 前端构建内容指纹、缓存复用、临时 dist 与原子替换。
- 中断导入 quarantine、recovery.json 和保留三份隔离样本。
- 自动迁移备份 API、完整性检查、备份轮换十份和 backup.ps1。
- 固定 10 MB 日志轮换与保留五份；只保留脱敏结构化日志要求。
- 未经实测的 41/45 首次通过率、2 分钟首例和 10 分钟整批硬阈值。
- 任意生产级身份、安全、部署、监控、容灾与外部系统集成。

这些设计没有被判定为错误。它们只是不能挤占本期真实运行闭环。未来只有出现明确触发条件，例如需要数据库结构升级保护、多用户使用、远程部署或长期无人值守运行时，才单独立项。

## 18. 最强反对意见

反对本规格的最强论据是：对一个 10 天本机演示，三次模型调用、九张表、五个数据端口、严格状态机和追加历史仍然偏重；一次大 Prompt、几张表和一个简单页面会更快。

该论据力度为强。它准确指出了本项目最大的交付风险不是功能不够，而是工程边界过多。

本规格仍保留这些设计，原因不是追求生产级架构，而是它们分别对应已经明确要求的不可替代结果：

- 三阶段调用让感知、归因、策略能够分别限制输入、校验证据和定位失败。
- 九表把当前业务结果、首次批次历史、单案例重跑、模型尝试和人工结果分开，才能同时做到刷新恢复、追溯和不覆盖。
- 五个 M1 端口是同一模块内的小边界，不是五个服务，用于四人并行时阻止 M3 直接写 SQL。
- 状态机和原子发布防止页面永久停在分析中、显示半个决策包或在重跑后继续审核旧结果。

真正应当删除的是不会改变上述结果的生产级加固和假精确阈值，本文已经删除或降级。若真实 PoC 证明三次调用的费用或等待时间无法接受，届时只重新评估“归因与策略是否合并为一次调用”；PerceptionResult、AttributionResult、DecisionPackage、证据边界和持久化结果仍保持分离。

## 19. 执行入口

本规格当前状态为 `TECH_SPEC_READY`，可以执行 Task，但不能据此声称产品已经完成。第一张卡固定为 M3-01；其通过四人共同验收后，同时开放 M1-01、M2-01、M3-02、M4-01。执行阶段不再开展大规模需求追问，不改写已经冻结的产品、数据、模型、接口、状态和验收边界。
