"""M1-09 测试公共夹具：sys.path 引导与逻辑源目录定位。

- 把仓库根加入 sys.path，使测试可 `from tools.data_preparation import …`；
- source_root 夹具：优先取 PSIT_SOURCE_ROOT 环境变量，其次尝试仓库同级 source_data；
  普通全量测试缺失时跳过，M1-09 正式任务缺失时明确失败。
- dataset 夹具：会话级构建一次，供双包校验类测试复用。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

LEGACY_SOURCE_SUBPATH = (
    Path("项目文档") / "PSIT项目审查" / "source_data" / "ecommercedata-main"
)
REQUIRED_SOURCE = Path("dataprocessing") / "output" / "data_with_context.csv"


def _candidate_source_roots() -> list[Path]:
    candidates: list[Path] = []
    env = os.environ.get("PSIT_SOURCE_ROOT")
    if env:
        return [Path(env)]
    candidates.append(REPO_ROOT.parent / "source_data" / "ecommercedata-main")
    candidates.append(REPO_ROOT.parent / LEGACY_SOURCE_SUBPATH)
    return candidates


@pytest.fixture(scope="session")
def source_root() -> Path:
    """逻辑源目录；找不到时整体跳过依赖它的用例。"""
    for candidate in _candidate_source_roots():
        if (candidate / REQUIRED_SOURCE).exists():
            return candidate.resolve()
    message = (
        "缺少逻辑源目录：请设置 PSIT_SOURCE_ROOT 环境变量后重跑，"
        "或把 source_data/ecommercedata-main 放在仓库同级目录"
    )
    if os.environ.get("PSIT_REQUIRE_SOURCE_ROOT") == "1":
        pytest.fail(message)
    pytest.skip(message)


@pytest.fixture(scope="session")
def dataset(source_root: Path, tmp_path_factory):
    """会话级构建一次（约 5 秒），返回 BuildResult。"""
    from tools.data_preparation.builder import build_dataset

    out = tmp_path_factory.mktemp("m109_dataset")
    return build_dataset(source_root, out)
