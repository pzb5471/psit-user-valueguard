# M1-09 负向测试夹具

| 文件 | 说明 |
|---|---|
| `not_a_zip.zip` | 文本内容伪装的 ZIP（非合法 zip 字节），`ZipImportStage` 应拒绝为“无法解析 ZIP 文件”。 |

负向断言见 `tools/data_preparation/tests/test_builder.py::test_stage_rejects_broken_zip`。
