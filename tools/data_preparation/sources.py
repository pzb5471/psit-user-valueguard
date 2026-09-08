"""M1-09 源数据加载：清洗后主表、客服任务 JSONL 与图片索引（技术实施规格 5.2）。

- 清洗后主表 `dataprocessing/output/data_with_context.csv` 是唯一组案主入口；
  第一列为无字段名旧索引列，必须丢弃（规格 5.2）。
- 客服任务 `data/service_tasks.json` 实际为 JSONL，一行一个任务；答案性质字段只
  用于密封参考，绝不进入运行包。
- 图片文件按任务 `image_paths` 的相对路径定位，路径均相对逻辑源目录。

本模块不引入除标准库以外的依赖；金额一律使用 Decimal（规格 5.5）。
"""

from __future__ import annotations

import csv
import json
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

CSV_RELATIVE_PATH = "dataprocessing/output/data_with_context.csv"
TASKS_RELATIVE_PATH = "data/service_tasks.json"
IMAGES_RELATIVE_PATH = "data/images/"

CSV_DATASET_NAME = "data_with_context"
TASKS_DATASET_NAME = "service_tasks"

# 主表 19 个业务字段之外的无字段名旧索引列键（cs 的 DictReader 以空串命名）。
_OLD_INDEX_KEYS = frozenset({""})


class SourceRootError(FileNotFoundError):
    """逻辑源目录缺少 M1-09 必需的源文件。"""


def require_source_root(source_root: Path) -> Path:
    """校验逻辑源目录结构，返回规范化根路径；缺文件时抛出明确错误。"""
    root = Path(source_root).resolve()
    missing = [
        rel
        for rel in (CSV_RELATIVE_PATH, TASKS_RELATIVE_PATH, IMAGES_RELATIVE_PATH)
        if not (root / rel).exists()
    ]
    if missing:
        raise SourceRootError(
            f"逻辑源目录缺少必需文件：{', '.join(missing)}（--source-root 指向"
            f"{root}）"
        )
    return root


def load_csv_rows(csv_path: Path) -> list[dict[str, str]]:
    """读取清洗后主表：丢弃旧索引列，保留 19 个业务字段（规格 5.2）。"""
    rows: list[dict[str, str]] = []
    with csv_path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for raw in reader:
            row = {key: value for key, value in raw.items() if key not in _OLD_INDEX_KEYS}
            rows.append(row)
    if not rows:
        raise SourceRootError(f"清洗后主表 {csv_path} 没有任何数据行")
    return rows


def load_tasks(tasks_path: Path) -> dict[str, dict[str, object]]:
    """读取客服任务 JSONL，按键 task_id 建索引；重复 task_id 视为源数据错误。"""
    by_id: dict[str, dict[str, object]] = {}
    with tasks_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            task_id = record.get("task_id")
            if not isinstance(task_id, str) or not task_id:
                raise SourceRootError("service_tasks.json 记录缺少非空 task_id")
            if task_id in by_id:
                raise SourceRootError(f"service_tasks.json 出现重复 task_id：{task_id}")
            by_id[task_id] = record
    if not by_id:
        raise SourceRootError(f"客服任务 {tasks_path} 没有任何记录")
    return by_id


def to_iso_timestamp(cell: str) -> str:
    """CSV 时间 '2017-10-02 10:56:33' → ISO 8601 '2017-10-02T10:56:33'（规格 5.5）。"""
    return cell.strip().replace(" ", "T")


def parse_timestamp(cell: str) -> datetime:
    """把 CSV 时间单元解析为 datetime（用于 RFM 与快照）。"""
    return datetime.fromisoformat(cell.strip())


def non_empty(cell: str | None) -> bool:
    """CSV 可空时间单元：空白视为不存在。"""
    return bool(cell and cell.strip())


def image_paths_of(task: dict[str, object]) -> list[str]:
    """任务图片引用列表；task[image_paths] 为 JSON 数组（规格 5.2）。"""
    value = task.get("image_paths", [])
    if not isinstance(value, list):
        raise SourceRootError("service_tasks.json 的 image_paths 必须是数组")
    return [str(item) for item in value]


def iter_tasks(by_id: dict[str, dict[str, object]]) -> Iterable[dict[str, object]]:
    """按 task_id 升序遍历全部任务（确定性顺序）。"""
    for task_id in sorted(by_id):
        yield by_id[task_id]
