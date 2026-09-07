"""M1-09 测试公共夹具：sys.path 引导与逻辑源目录定位。

- 把仓库根加入 sys.path，使测试可 `from tools.data_preparation import …`；
- source_root 夹具：优先取 PSIT_SOURCE_ROOT 环境变量，其次尝试仓库旁默认源目录；
  两者都缺失时跳过（而不是失败），单测类用例不依赖源目录。
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

SOURCE_SUBPATH = Path("项目文档") / "PSIT项目审查" / "source_data" / "ecommercedata-main"
REQUIRED_SOURCE = Path("dataprocessing") / "output" / "data_with_context.csv"


def _candidate_source_roots() -> list[Path]:
    candidates: list[Path] = []
    env = os.environ.get("PSIT_SOURCE_ROOT")
    if env:
        candidates.append(Path(env))
    candidates.append(REPO_ROOT.parent / SOURCE_SUBPATH)
    return candidates


@pytest.fixture(scope="session")
def source_root() -> Path:
    """逻辑源目录；找不到时整体跳过依赖它的用例。"""
    for candidate in _candidate_source_roots():
        if (candidate / REQUIRED_SOURCE).exists():
            return candidate.resolve()
    pytest.skip(
        "缺少逻辑源目录：请设置 PSIT_SOURCE_ROOT 环境变量后重跑，"
        "或把仓库放到含 项目文档/PSIT项目审查/source_data 的目录旁"
    )


@pytest.fixture(scope="session")
def dataset(source_root: Path, tmp_path_factory):
    """会话级构建一次（约 5 秒），返回 BuildResult。"""
    from tools.data_preparation.builder import build_dataset

    out = tmp_path_factory.mktemp("m109_dataset")
    return build_dataset(source_root, out)
