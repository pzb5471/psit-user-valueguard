"""仓库自带演示包验收：克隆后无需私有源数据即可导入固定 10 案例。"""

from __future__ import annotations

import hashlib
from pathlib import Path

from app.contracts.data import PackageType
from app.modules.data.importing.zip_stage import ZipImportStage

REPO_ROOT = Path(__file__).resolve().parents[3]
DEMO_PACKAGE = REPO_ROOT / "demo" / "demo_batch_v1.zip"
DEMO_PACKAGE_SHA256 = "a7968fdf3e49010dbae73bb4db14611948ed00a37d6c7cf31b365058b559d3f2"


def test_repository_demo_package_is_fixed_and_importable(tmp_path: Path) -> None:
    assert DEMO_PACKAGE.is_file(), "仓库缺少 demo/demo_batch_v1.zip"
    raw = DEMO_PACKAGE.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == DEMO_PACKAGE_SHA256

    result = ZipImportStage(tmp_root=tmp_path).stage(
        raw,
        source_filename=DEMO_PACKAGE.name,
    )

    assert result.ok, result.rejections
    assert result.package_type == PackageType.DEMO
    assert result.case_count == 10
    assert result.is_mock is True
