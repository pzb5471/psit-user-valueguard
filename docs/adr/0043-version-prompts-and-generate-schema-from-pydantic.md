# Prompt 独立版本化，运行 Schema 从 Pydantic 生成

三个阶段 Prompt 分别保存在 `prompts/perception/v1.md`、`prompts/attribution/v1.md` 和 `prompts/strategy/v1.md`。每份文件只描述该阶段的职责、允许输入、禁止推断、证据规则、不确定性、JSON 输出和禁用内容，不包含 API Key、密封验收答案或固定案例答案。

Pydantic 模型是字段结构的唯一来源。运行时由程序从 `PerceptionResult`、`AttributionResult` 或 `DecisionPackage` 模型生成 JSON Schema 并注入对应 Prompt，避免手写字段清单与代码模型漂移。每次 `model_call` 保存 Prompt 语义版本、文件 SHA-256 和输出合同版本。

Prompt 内容变化必须形成明确版本变更并通过 Prompt 装配、Schema 快照和固定案例回归测试。业务页面不提供 Prompt 编辑器，模型参数和 Prompt 不由运营人员配置。
