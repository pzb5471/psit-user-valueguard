"""M1-09 源数据加载单元测试（技术实施规格 5.2）：旧索引列丢弃、JSONL 索引、时间转换与目录校验。"""

import pytest

from tools.data_preparation.sources import (
    SourceRootError,
    image_paths_of,
    load_csv_rows,
    load_tasks,
    parse_timestamp,
    require_source_root,
    to_iso_timestamp,
)


def test_load_csv_rows_drops_unnamed_index_column(tmp_path) -> None:
    csv_path = tmp_path / "data_with_context.csv"
    csv_path.write_text(
        ",order_id,customer_unique_id,conversation\n"
        "0,o1,c1,你好\n"
        "1,o2,c2,在吗\n",
        encoding="utf-8",
    )
    rows = load_csv_rows(csv_path)
    assert len(rows) == 2
    assert "" not in rows[0]
    assert set(rows[0]) == {"order_id", "customer_unique_id", "conversation"}


def test_load_csv_rows_header_only_raises(tmp_path) -> None:
    csv_path = tmp_path / "empty.csv"
    csv_path.write_text("order_id\n", encoding="utf-8")
    with pytest.raises(SourceRootError, match="没有任何数据行"):
        load_csv_rows(csv_path)


def test_load_tasks_indexes_by_task_id(tmp_path) -> None:
    tasks_path = tmp_path / "service_tasks.json"
    tasks_path.write_text(
        '{"task_id": "t1", "conversation": "a"}\n'
        '{"task_id": "t2", "conversation": "b"}\n',
        encoding="utf-8",
    )
    by_id = load_tasks(tasks_path)
    assert set(by_id) == {"t1", "t2"}
    assert by_id["t1"]["conversation"] == "a"


def test_load_tasks_duplicate_task_id_raises(tmp_path) -> None:
    tasks_path = tmp_path / "dup.json"
    tasks_path.write_text(
        '{"task_id": "t1", "conversation": "a"}\n{"task_id": "t1", "conversation": "b"}\n',
        encoding="utf-8",
    )
    with pytest.raises(SourceRootError, match="重复 task_id"):
        load_tasks(tasks_path)


def test_load_tasks_missing_task_id_raises(tmp_path) -> None:
    tasks_path = tmp_path / "bad.json"
    tasks_path.write_text('{"conversation": "a"}\n', encoding="utf-8")
    with pytest.raises(SourceRootError, match="task_id"):
        load_tasks(tasks_path)


def test_to_iso_timestamp() -> None:
    assert to_iso_timestamp("2017-10-02 10:56:33") == "2017-10-02T10:56:33"


def test_parse_timestamp() -> None:
    assert parse_timestamp("2017-10-02 10:56:33").year == 2017
    assert parse_timestamp("2017-10-02 10:56:33").minute == 56


def test_image_paths_of() -> None:
    task = {"task_id": "t1", "image_paths": ["data/images/01.jpg"]}
    assert image_paths_of(task) == ["data/images/01.jpg"]


def test_require_source_root_missing_raises(tmp_path) -> None:
    with pytest.raises(SourceRootError, match="缺少必需文件"):
        require_source_root(tmp_path / "missing-root")
