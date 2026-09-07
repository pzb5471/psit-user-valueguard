# M1-09 双批 ZIP 构建说明

本目录不存放 ZIP 产物：DEMO/ACCEPTANCE 两个标准 ZIP 属于运行数据，由组包程序
构建到 `runtime_data/mock_dataset_v1/`（ADR-0033，不入 Git）。测试通过
`tools/data_preparation/tests/conftest.py` 的 `dataset` 会话夹具在临时目录重建后
逐项断言。

| 批次 | 案例数 | ZIP 文件名 | 说明 |
|---|---|---|---|
| DEMO | 10 | `demo_batch_v1.zip` | 规格 5.5 演示批次（含图片案例） |
| ACCEPTANCE | 5 | `acceptance_batch_v1.zip` | 验收批次（000003/000006/000009/000051/000074） |

重建命令（仓库根目录）：

    python -m tools.data_preparation --source-root <逻辑源目录>

ZIP 结构（规格 5.4）：`manifest.json`、`checksums.json`、`cases/<case_id>.json`、
`assets/<case_id>/NN.<ext>`（扩展名按图片魔数推导）。结构、泄漏、媒体与清单
一致性断言见 `tools/data_preparation/tests/test_builder.py`。
