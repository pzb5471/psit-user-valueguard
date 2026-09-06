# M1-01 数据合同最小样例

本目录保存 M1-01（`backend/app/contracts/data.py`）的合法与非法最小样例，供
`tests/contracts/data/` 合同测试、M1-03/M1-04 导入校验与 M1-09 组包程序复用。

| 文件 | 说明 |
|---|---|
| `valid_case_input.json` | 符合 CaseInput v1 的完整合法案例：两个文本证据、一个图片证据、四个行为证据，金额与时间均为十进制定点字符串 / ISO 8601。 |
| `valid_manifest.json` | 符合 batch_manifest.v1 的合法清单（2 个案例，`case_files` 升序）。 |
| `valid_checksums.json` | 相对路径 → 小写 SHA-256 的合法校验和对象（不含自身，键升序）。 |
| `invalid_case_input_banned_field.json` | 合法案例顶层混入答案字段 `key_answer`，演示对答案泄漏字段的拒绝。 |
| `invalid_manifest_mismatch.json` | `case_count`（3）与 `case_files` 实际数量（2）不一致。 |
| `invalid_checksums_self.json` | 包含自身条目 `checksums.json`。 |

更多拒绝场景（宽松类型、重复 evidence_id、缺失来源、路径越界、错误哈希、manifest
顺序与上限等）由 `tests/contracts/data/test_data_contracts.py` 基于本目录合法样例的
变异输入覆盖。

注意：ZIP 内 JSON 的“UTF-8、LF、稳定键顺序、无意义空白最小化”由组包程序（M1-09）
负责；本目录样例为便于人工评审使用带缩进的 UTF-8 JSON，键顺序已与合同字段顺序一致。