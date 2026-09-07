"""反向依赖负向夹具：共享数据合同不得引入框架或模块实现（规格第 6 节）。

data.py 允许依赖标准库、typing 与 Pydantic；以最严格形式断言：导入
app.contracts.data 后，任何框架与模块实现都不得出现在 sys.modules。
"""

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

BANNED_MODULES = (
    "fastapi",
    "uvicorn",
    "sqlalchemy",
    "alembic",
    "pydantic_settings",
    "httpx",
    "pytest",
    "zai_sdk",
    "zhipuai",
)

PROBE = (
    "import sys\n"
    "import app.contracts.data\n"
    f"banned = {BANNED_MODULES!r}\n"
    "loaded = set(banned) & set(sys.modules)\n"
    "assert not loaded, f'contracts 导入了被禁止的模块: {sorted(loaded)}'\n"
)


def test_data_import_no_frameworks() -> None:
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT / "backend")}
    result = subprocess.run(
        [sys.executable, "-c", PROBE],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, result.stderr
