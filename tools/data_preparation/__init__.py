"""M1-09 固定数据快照、案例包与密封验收集生成程序（技术实施规格 5.2—5.6；任务卡 M1-09）。

本包只负责确定性数据处理：读取清洗后主表与客服任务，复算 RFM，构造 10 案例演示
ZIP 与 5 案例验收 ZIP，并输出物理分离的密封参考与可复算内部报告。所有输出写入
runtime_data/mock_dataset_v1/（ADR-0033：runtime_data/ 不入 Git），不修改产品运行模块。

运行方式（在仓库根目录）：

    python -m tools.data_preparation --source-root <逻辑源目录>

其中 <逻辑源目录> 是包含 `dataprocessing/output/data_with_context.csv`、
`data/service_tasks.json` 与 `data/images/` 的目录；代码不写死成员电脑绝对路径。
"""

from .builder import BuildResult, build_dataset

__all__ = ["BuildResult", "build_dataset"]
__version__ = "mock_dataset_builder.v1"
