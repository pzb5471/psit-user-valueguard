# M1-09 组包报告（report.json）

报告由 `python -m tools.data_preparation --source-root <逻辑源目录>` 生成，写入
`runtime_data/mock_dataset_v1/report.json`（ADR-0033：runtime_data/ 不入 Git），
用于人工核验与可复算对照，不被产品运行模块读取。

| 顶层字段 | 说明 |
|---|---|
| `schema_version` | `mock_dataset_report.v1` |
| `builder_version` | `mock_dataset_builder.v1` |
| `data_version` | `mock_dataset_v1` |
| `source_snapshot_at` | RFM 快照时间（源数据最大下单时间） |
| `rfm` | `high_value_rule_v1` 的阈值（r_p75/m_p80/m_p50）与客户/高价值数量（全量复算） |
| `source_manifest_sha256` | 所有实际使用源文件（主表、任务与选中图片）的字节摘要 |
| `mapping_manifest_sha256` | mapping_manifest.json 字节摘要 |
| `packages` | MVP（10 案例）与 ACCEPTANCE（5 案例）的文件名、SHA-256 与数量 |
| `cases` | 逐案例概要（文本/图片/行为证据数与图片媒体类型） |
| `control_case` | 普通客户对照案例标识与高价值标记 |

同目录关联文件：

- `mvp_batch_v1.zip` / `acceptance_batch_v1.zip`：运行 ZIP（结构见
  `tools/data_preparation/tests/fixtures/batches/README.md`）；
- `mapping_manifest.json`：task_id → case_id / order_id / 客户 / 资产路径映射；
- `source_manifest.json`：实际使用的源文件相对路径与 SHA-256；
- `rfm_profiles.jsonl`：逐客户 R/F/M、判定与理由的可复算内部产物；
- `control_case.json`：普通客户对照 CaseInput（不入 ZIP）；
- `sealed/`：每个案例的答案性质参考（不入 ZIP）。

重建与断言：生成代码见 `tools/data_preparation/builder.py`，测试见
`tools/data_preparation/tests/test_builder.py` 与 `test_rfm.py`。
