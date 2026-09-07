# M1-09 密封参考目录

运行 `python -m tools.data_preparation` 后，每个案例写一份
`runtime_data/mock_dataset_v1/sealed/<case_id>.json`（ADR-0033，不入 Git），只含
`case_builder.SEALED_KEYS` 列出的答案性质字段（`key_answer`、`label`、
`database_gt`、`trajectory`、`user_profile_st1`、`user_profile`、`question_type`、
`user_address`、`database`、`first_query`），并整体放入 `source` 键下；对话、
图片与原任务记录绝不进入密封参考，答案性质字段也绝不进入运行 ZIP。

| 文件 | 说明 |
|---|---|
| `sealed_case_template.json` | 密封参考的结构模板（键名与嵌套示意；字段值为占位）。 |

结构断言见 `tools/data_preparation/tests/test_builder.py` 的
`test_sealed_reference_files_cover_all_cases`。
