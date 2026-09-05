"""反向依赖负向夹具：共享状态合同不得引入框架或模块实现（规格第 6 节）。

规格允许共享合同依赖标准库、typing 与 Pydantic；states.py 本身只需要标准库，
因此以最严格形式断言：导入 states 后，任何框架与模块实现都不得出现在 sys.modules。
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
    "import app.contracts.states\n"
    f"banned = {BANNED_MODULES!r}\n"
    "loaded = set(banned) & set(sys.modules)\n"
    "assert not loaded, f'contracts 导入了被禁止的模块: {sorted(loaded)}'\n"
)


def test_states_import_no_frameworks() -> None:
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT / "backend")}
    result = subprocess.run(
        [sys.executable, "-c", PROBE],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, result.stderr
