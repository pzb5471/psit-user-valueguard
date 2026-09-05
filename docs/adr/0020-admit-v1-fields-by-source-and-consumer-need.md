# v1 字段只在有来源且有消费者时进入合同

## 决定

MVP 字段采用四道准入条件。满足任意一类且下游确实使用，才进入 v1：

1. 现有数据直接提供的原始观察。
2. 能由固定代码从现有数据复算的派生事实。
3. 由系统运行确定产生的版本、标识、哈希、来源、状态和时间等运行元数据。
4. 产品必须交付、能够引用现有证据的 Agent 判断。

无法说明来源、生成规则或下游消费者的字段不进入 v1。某个概念存在，不代表必须拆成单独字段；能由已有内容确定推导的状态不重复保存，某案例不存在的可选内容直接省略，不用大量 `null`、空数组和套话填满结构。

这条规则并不要求所有输出字段都必须是源数据列。事件摘要、当前情绪、风险原因和处理建议本来就是 Agent 应完成的判断，但必须引用运行包中的证据，并且页面、下一阶段或人工复核确实需要它。

## 当前数据能够提供的输入

清洗后主表 `data_with_context.csv` 当前直接提供以下可用信息：

- 订单与客户标识：`order_id`、`customer_id`、`customer_unique_id`。
- 订单状态与时间：`order_status`、下单、批准、交承运、实际送达、预计送达时间。
- 付款：`payment_value`，同一订单多行需要先聚合。
- 售后证据：`conversation`、`image_paths`。
- 地理字段和付款方式虽然存在，但不是 v1 风险判断必需字段，不进入 Agent 视图。
- 主表首个无字段名索引列在组包时丢弃；`image_paths` 从 Python 列表字符串转换为标准数组。

`service_tasks.json` 实际是逐行 JSON。`conversation` 和 `image_paths` 只在解析、脱敏和重建证据编号后进入运行包。以下字段不得原样进入运行环境：

- 答案或答案泄漏：`mood`、`reason`、`solution`、`image_verification`、`key_answer`、`label`、`database_gt`、`trajectory`、`user_profile_st1`、`user_profile`、`question_type`。
- 未规范化或重复数据：`user_address`、`database`、`first_query`。
- `task_id`、`snapshot_id` 只可转换成内部来源引用，不作为 Agent 业务输入。

当前清洗后数据可由程序确定生成 R、F、M、高价值客户结论、聚合付款总额、脱敏标识、稳定证据编号、文件哈希和模拟关系标记。当前数据不能稳定支持售后案例创建时间、消息时间、币种、行为变化、近期与基准期窗口，因此这些字段不进入 v1。

## 收紧后的 CaseInput v1

顶层只保留：

- `schema_version`
- `data_version`
- `batch_id`
- `case_id`
- `data_identity`
- `primary_order`
- `customer`
- `customer_value`
- `evidence`
- `provenance`

`primary_order` 只保存订单引用、订单状态、下单时间、源中存在的可选履约时间和付款总额。`evidence` 分为 `text_items`、`image_items` 和 `behavior_items`。每条证据共同保存稳定编号、数据身份、关系身份、来源和哈希；时间只在相应源数据实际提供时出现。

不设置 `case_trigger`、`modality_status`、`currency`、`payment_parts`、`simulated_wait_minutes`、`behavior_change`、`window_start` 和 `window_end`。案例触发事件由感知阶段还原，模态状态由证据数组和读取结果确定，系统排序使用导入成功时生成的 `imported_at`。

由于交易、对话和图片属于 `mock_mapped` 组合，完整订单事实用于来源追溯；只有固定案例经过人工检查、确认与售后对话语义不冲突的事实才进入 Agent 受限视图。高价值客户结论是 v1 行为模态必定进入决策的内容。

## 收紧后的 Agent 输出合同

### PerceptionResult

顶层只保留：

- `schema_version`
- `case_id`
- `events`
- `image_observations`
- `emotion`
- `missing_evidence`

事件保存事件编号、类别、摘要、陈述状态、解决状态、支持证据，以及实际存在时才出现的冲突证据和不确定性。逐图片观察保存图片证据编号、分析状态、最多三条可观察事实、与客户陈述的关系、关联文本证据和按需出现的不确定性。情绪只保存平静、不耐烦或无法判断、简短解释、客户文本证据和按需出现的不确定性。

不重复输出 `text_observations` 和 `behavior_observations`，不要求独立的 `alternative_interpretations`、`warnings`、情绪变化或目标情绪。图片不要求固定主体分类、异常位置和可见程度。

### AttributionResult

顶层只保留：

- `schema_version`
- `case_id`
- `risk_summary`
- `primary_cause`
- 按需出现的 `alternative_cause`

主要原因保存受控类别、解释和支持证据；存在反证或不确定性时才增加相应字段。只有证据确实同时指向另一类原因时才允许一个备选原因。原因合同使用物流履约、商品、退货退款、服务沟通、价格或权益、其他六个业务类别，另设非原因兜底值 `INSUFFICIENT_EVIDENCE`；隐藏 `reason` 只用于验收映射，不进入运行 Agent。

### DecisionPackage

顶层只保留：

- `schema_version`
- `case_id`
- `intervention_level`
- `priority_reason`
- `actions`
- `communication_points`
- 按需出现的 `caution_note`

每个动作只保存动作类型、具体描述、原因、支持证据和按需出现的前置条件。动作最多三项，沟通重点最多三项。`requires_human_approval` 恒由产品门禁执行，不由模型重复输出；`prohibited_claims` 属于静态策略校验，不是模型输出；`manual_review_focus`、通用 `limitations` 和包级重复证据编号不进入 v1。

## 影响

这套合同降低了单次模型返回字段数量、空值数量和重复内容，能够直接减少 JSON 结构校验失败、无依据补写和 Mock 关系冲突。代价是未来接入真实业务数据时需要新增合同版本，而不是直接复用提前猜出的字段。这个代价可控；v1 的首要目标是让当前 15 个固定案例稳定、可追溯地跑通。

最强反对意见是：字段收得过窄会增加以后扩展成本。该意见力度为中等。版本化合同本来就允许 v2 增加币种、真实工单时间和行为窗口；现在提前保留无来源字段，只会把未来的不确定性变成当前的失败点。
