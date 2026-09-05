# PSIT HTTP API 合同

## 1. 总则

M3 通过 `/api/v1` 向 M4 提供十个固定接口。单项查询直接返回资源，列表返回 `items` 和 `total`，写操作返回保存或接受后的业务资源。业务 JSON 不使用无信息量的 `success: true` 外壳，也不返回数据库对象、运行编号、Prompt、Token、日志或供应商响应。

请求和响应字段使用 `snake_case`。FastAPI Pydantic 是 OpenAPI 真源，M4 使用 `openapi-typescript` 生成并提交 TypeScript 类型，使用 `openapi-fetch` 请求。

## 2. 十个接口

| 方法 | 地址 | 用途 | 成功响应 |
|---|---|---|---|
| POST | `/api/v1/batches` | 上传并导入一个标准 ZIP | 新建 `201`，重复包 `200`；正文均为 `BatchWorkspaceView` |
| GET | `/api/v1/batches` | 查询历史批次 | `200 BatchListView` |
| GET | `/api/v1/batches/{batch_id}` | 查询批次摘要和进度 | `200 BatchWorkspaceView` |
| POST | `/api/v1/batches/{batch_id}/runs` | 开始批量分析 | `202 BatchWorkspaceView`；幂等命中仍返回当前业务视图 |
| GET | `/api/v1/batches/{batch_id}/cases` | 查询案例队列 | `200 CaseQueueView` |
| GET | `/api/v1/batches/{batch_id}/cases/{case_id}` | 查询案例详情 | `200 CaseDetailView` |
| POST | `/api/v1/batches/{batch_id}/cases/{case_id}/reruns` | 重新分析允许重跑的案例 | `202 CaseDetailView`；幂等命中仍返回当前业务视图 |
| POST | `/api/v1/batches/{batch_id}/cases/{case_id}/reviews` | 提交人工最终确认 | 新建 `201`，相同 `submission_id` 重试 `200`；正文为 `ReviewResultView` |
| GET | `/api/v1/batches/{batch_id}/cases/{case_id}/evidence/{evidence_id}/content` | 读取证据图片 | `200` 图片文件流和真实媒体类型 |
| GET | `/api/v1/health` | 查询应用、数据库和分析能力 | `200 HealthView` |

开始分析和重新分析立即返回，不等待 GLM。前端只按 `batch_id` 和 `case_id` 轮询业务视图，业务 API 不返回 `batch_run_id`、`case_run_id` 或其他运行编号。

## 3. 请求合同

### 3.1 上传批次

`POST /api/v1/batches` 使用 `multipart/form-data`，只接受一个名为 `file` 的 ZIP 文件字段。不接受服务器路径、多个文件、数据版本表单值或前端声明的校验通过标记。

浏览器快速检查不改变后端权威校验。FastAPI 必须重新检查大小、ZIP 格式、路径安全、清单、校验值、案例合同、关系与来源身份、答案泄漏字段和实际引用文件。

### 3.2 开始批量分析

`POST /api/v1/batches/{batch_id}/runs` 没有 JSON 请求体。目标批次由路径唯一确定，模型参数、并发、Prompt 和运行编号不得由页面传入。

### 3.3 重新分析案例

`POST /api/v1/batches/{batch_id}/cases/{case_id}/reruns` 没有 JSON 请求体。后端根据案例当前状态判断是否允许重跑，并按当前正式配置运行；页面不能传模型参数、Prompt 或历史运行编号。

### 3.4 人工确认

人工确认使用以 `outcome` 为区分字段的四种严格 Pydantic 请求。共同字段为：

- `submission_id`：前端为一次业务提交生成的 UUID；网络重试必须复用。
- `review_token`：从当前案例详情原样带回的不可读并发校验值。
- `outcome`：四种人工结果之一。

四种请求规则：

| `outcome` | 必须提供 | 禁止额外提供 |
|---|---|---|
| `APPROVED` | 共同字段 | 人工最终结果和审核原因 |
| `MODIFIED_AND_APPROVED` | 最终介入等级、最终原因类别、最终处理动作、必填修改原因；执行说明按需出现 | 目录外动作和自由 JSON |
| `REJECTED_WITH_JUDGMENT` | 人工最终介入等级、最终原因类别、最终处理动作、必填驳回原因；执行说明按需出现 | 只有“驳回”而没有人工判断 |
| `INSUFFICIENT_EVIDENCE` | 必填证据缺口说明，保存到审核原因 | 人工编造的确定原因和处理动作 |

修改和驳回提交完整人工最终结果，不提交 JSON Patch 或零散字段位置。动作只能来自当前只读动作目录，数量不超过三项。

## 4. review_token

`review_token` 解决两个同时存在的要求：页面不能看到运行编号，后端又必须防止用户审核已经被重跑替换的旧结果。

固定行为：

- 只在案例允许人工确认时出现在 `CaseDetailView`，页面不得展示其内容。
- 它是不可解析的并发校验值，不是 `case_run_id`、数据库主键或数据版本。
- 后端根据当前案例、当前运行和当前更新时间生成或验证，不需要新增用户可编辑字段。
- 当前结果因重新分析而变化时 Token 必须变化。
- 提交缺少 Token 的审核请求按字段合同错误处理；Token 与当前结果不一致时返回 `409 STALE_CASE_RESULT`。
- M1 在保存审核的同一事务内再次比较当前运行，最终 `reviews.case_run_id` 仍关联内部真实运行。

Token 只用于并发一致性，不是登录、权限或防攻击凭证。

## 5. 查询、筛选和排序

### 5.1 历史批次

```text
GET /api/v1/batches?limit=20&offset=0
```

- `limit` 默认 20，最小 1，最大 100。
- `offset` 默认 0，最小 0。
- 按 `imported_at` 倒序，再按稳定 `batch_id` 排序。
- v1 不提供批次名称搜索、删除和任意排序参数。

### 5.2 案例队列

```text
GET /api/v1/batches/{batch_id}/cases
    ?status=PENDING_REVIEW
    &intervention_level=MUST_INTERVENE
    &limit=50
    &offset=0
```

- `status` 和 `intervention_level` 各允许一个已冻结枚举值，均可省略。
- `limit` 默认 50，最小 1，最大 100；`offset` 默认 0。
- 后端始终执行介入等级、`imported_at`、`case_id` 的冻结排序规则，页面不能传任意 `sort_by`。
- M4 把筛选和分页位置写入 URL。
- v1 不提供客户全文搜索、任意字段排序和复杂组合筛选器。

## 6. 响应 DTO

### 6.1 BatchWorkspaceView

- `batch_id`
- `source_filename`
- `is_mock`
- `status`
- `case_count`
- `evidence_count`
- `analysis_succeeded_count`
- `error_count`
- `imported_at`
- `can_start_analysis`
- 按需出现的 `analysis_unavailable_message`

`status` 只使用 `PENDING_ANALYSIS`、`ANALYZING`、`COMPLETED`、`COMPLETED_WITH_ERRORS`。`analysis_succeeded_count` 和 `error_count` 表示案例当前投影，人工重跑时随当前案例状态更新；首次批量运行历史只保存在内部 `batch_runs`。不得包含数据版本、Schema 版本、ZIP 路径、校验值或批次运行编号。

### 6.2 BatchListView

- `items: list[BatchWorkspaceView]`
- `total`

### 6.3 CaseQueueItemView

- `case_id`
- `customer_display_id`
- `is_high_value`
- 按需出现的 `risk_summary`
- 按需出现的 `intervention_level`
- 按需出现的 `priority_reason`
- `status`
- `has_evidence_conflict`
- `has_insufficient_evidence`
- `has_modality_failure`

### 6.4 CaseQueueView

- `items: list[CaseQueueItemView]`
- `total`

### 6.5 CaseDetailView

- `batch_id`
- `case_id`
- `customer_display_id`
- `is_high_value`
- `customer_value_summary`
- `status`
- 按需出现的当前有效介入等级、风险摘要和主要原因
- 当前有效处理动作与沟通重点
- 按需出现的不确定性和证据缺口
- 当前结果实际引用的业务证据
- `is_mock`
- 按需出现的人工确认结果
- `can_rerun`
- `can_review`
- 只在 `can_review=true` 时出现的 `review_token`

证据对象可以包含请求内容所需的 `evidence_id`，但页面只显示“客户对话”“售后图片”“订单与客户价值事实”等业务名称，不显示编号本身。图片正文仍通过受控证据接口按需加载。

### 6.6 ReviewResultView

- `outcome`
- 当前有效人工介入等级
- 当前有效人工原因
- 当前有效人工处理动作
- 按需出现的执行说明
- 审核原因或证据缺口说明
- `created_at`

不得返回内部 `review_id`、`case_run_id` 或系统原始技术结果。系统原业务建议只在发生人工修改时通过案例详情的折叠业务视图读取。

### 6.7 HealthView

- `app_status`
- `database_status`
- `analysis_status`
- 业务可理解的 `message`

健康接口不返回 API Key、模型参数、供应商响应、数据库路径、异常堆栈或内部版本清单。

所有业务 DTO 省略不适用的可选字段，不输出大批 `null`。

## 7. 错误合同和状态码

所有 JSON 错误统一为 `BusinessError`：

- `code`
- 中文 `message`
- `object_type`
- 按需出现的 `object_id`
- 业务可理解的 `stage`
- `next_action`
- `trace_id`

| 状态码 | 使用边界 |
|---:|---|
| 200 | 查询成功，或相同上传、提交返回已有结果 |
| 201 | 新批次或新人工确认已经创建 |
| 202 | 分析或重跑已经接受，后台尚未完成 |
| 400 | ZIP 内容、目录、关系或运行输入合同不合格 |
| 404 | 批次、案例或证据不存在 |
| 409 | 身份冲突、已有活动批次、案例已完成或审核旧结果 |
| 413 | ZIP 超过 `upload.max_zip_bytes` |
| 415 | 上传文件或证据媒体类型不支持 |
| 422 | 请求字段类型、枚举、必填关系或联合类型不合格 |
| 503 | 分析服务当前不可用 |
| 500 | 未预期的内部技术异常 |

FastAPI 默认的 `422 detail` 和默认 `500` 页面必须在 API 边界转换成 `BusinessError`，不得形成第二种错误结构。

## 8. 禁止字段

业务响应不得包含：

- RFM 分数、分位、权重、阈值或计算方法。
- `data_version`、`schema_version`。
- 数据库整数主键。
- `batch_run_id`、`case_run_id`、阶段结果标识或模型调用标识。
- Agent 阶段、Prompt、Token、模型参数和供应商响应。
- 本机路径、文件校验值、内部数据身份结构和来源 JSON。
- 技术日志和原始 JSON 结果。

## 9. 合同测试

- 十个接口的每个成功状态和规定错误状态都必须进入 OpenAPI 快照。
- 新建与幂等命中的响应正文使用相同 DTO，只有状态码和业务状态不同。
- 列表的 `limit`、`offset`、过滤、总数和稳定排序使用参数化测试。
- 页面刷新和轮询不依赖运行编号。
- 案例重跑后旧 `review_token` 必须稳定返回 `STALE_CASE_RESULT`，并且数据库不产生审核记录。
- 四种人工确认请求分别验证必填、禁用字段、动作范围和幂等行为。
- 业务 DTO 使用白名单回归测试，ORM 新增字段不能自动进入 OpenAPI 或响应。
- 每种错误都验证没有堆栈、SDK 响应、密钥和绝对路径。

## 10. 最强反对意见

字段和状态码现在冻结得较具体，编码时可能暴露少量真实缺口。该意见力度中等。冻结的含义不是永不调整，而是禁止四个模块静默产生不同合同；新字段只有同时具备现有来源或确定生成规则、明确消费者和可执行验收时，才能通过独立合同变更进入 v1。
