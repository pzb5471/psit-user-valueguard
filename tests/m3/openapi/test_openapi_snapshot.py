"""OpenAPI 快照：生成式真源必须与已提交快照一致（M3-03 自动验收）。

合同有意变更时，用以下命令重新生成快照并把新文件与合同变更放进同一 PR：

    PYTHONPATH=backend uv run python -m tests.m3.openapi.regenerate_snapshot

或在仓库根执行：

    PYTHONPATH=backend uv run python tests/m3/openapi/regenerate_snapshot.py
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI

SNAPSHOT_PATH = Path(__file__).resolve().parent / "openapi_snapshot.json"


def test_openapi_matches_committed_snapshot(contract_app: FastAPI) -> None:
    committed = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    assert contract_app.openapi() == committed, (
        "OpenAPI 与已提交快照不一致。若为有意的合同变更，请重新生成 "
        "tests/m3/openapi/openapi_snapshot.json 并随合同变更一同提交评审。"
    )


def test_snapshot_contains_ten_paths_and_discriminated_review(
    contract_app: FastAPI,
) -> None:
    schema = contract_app.openapi()
    assert len(schema["paths"]) == 9  # health 与九个业务路径（POST/GET 计十条）

    review_path = schema["paths"]["/api/v1/batches/{batch_id}/cases/{case_id}/reviews"]
    body = review_path["post"]["requestBody"]["content"]["application/json"]["schema"]
    assert body.get("discriminator", {}).get("propertyName") == "outcome"
    assert len(body["oneOf"]) == 4  # 四种请求联合类型
