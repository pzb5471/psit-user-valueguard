"""仓库自带演示包验收：克隆后无需私有源数据即可导入固定 10 案例。"""

from __future__ import annotations

import hashlib
from pathlib import Path

from app.contracts.data import PackageType
from app.modules.data.importing.zip_stage import ZipImportStage

REPO_ROOT = Path(__file__).resolve().parents[3]
MVP_PACKAGE = REPO_ROOT / "mvp" / "mvp_batch_v1.zip"
MVP_PACKAGE_SHA256 = "958f7c8bc8b113ed4c1de943d52b09b88bd04e097234fc446e50e654bece301b"


def test_repository_mvp_package_is_fixed_and_importable(tmp_path: Path) -> None:
    assert MVP_PACKAGE.is_file(), "仓库缺少 mvp/mvp_batch_v1.zip"
    raw = MVP_PACKAGE.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == MVP_PACKAGE_SHA256

    result = ZipImportStage(tmp_root=tmp_path).stage(
        raw,
        source_filename=MVP_PACKAGE.name,
    )

    assert result.ok, result.rejections
    assert result.package_type == PackageType.MVP
    assert result.case_count == 10
    assert result.is_mock is True
