"""M1-03 公共夹具：独立临时暂存根与注入 ZipImportStage。

构造助手（make_case/make_entries/make_zip 等）在 zip_fixtures.py 中；
fixtures 必须留在 conftest.py 才能被 pytest 自动发现。
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def tmp_root(tmp_path: Path) -> Path:
    """独立临时暂存根（模拟 runtime_data/imports/tmp/）。"""
    return tmp_path / "runtime_data" / "imports" / "tmp"


@pytest.fixture
def stage(tmp_root: Path):
    """注入独立临时暂存根与默认上限的 ZipImportStage。"""
    from app.modules.data.importing.zip_stage import ZipImportStage

    return ZipImportStage(tmp_root=tmp_root)
