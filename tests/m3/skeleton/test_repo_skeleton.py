"""仓库骨架边界测试（M3-01 自动验收：目录边界、锁文件、Git 忽略）。"""

import json
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

FROZEN_DIRS = [
    "backend/app/contracts",
    "backend/app/modules/data",
    "backend/app/modules/analysis",
    "backend/app/modules/application",
    "frontend",
    "tests",
    "config",
    "scripts",
]

MODULE_DIRS = {"data", "analysis", "application"}
# docs/ 由 README 开工顺序第 2 条的文档 PR 同步进入仓库（规则、需求、CONTEXT、规格与追溯 ADR）。
ALLOWED_TOP_LEVEL_DIRS = {"backend", "config", "docs", "frontend", "scripts", "tests", "tools"}
ALLOWED_TOP_LEVEL_FILES = {
    ".gitignore",
    ".python-version",
    "AGENTS.md",
    "CONTEXT.md",
    "pyproject.toml",
    "uv.lock",
    "高价值客户异常售后决策支持MVP需求文档.md",
}
SCRIPTS = ["bootstrap.ps1", "dev.ps1", "start.ps1", "test.ps1"]


def git_tracked() -> list[str]:
    # core.quotepath=off 让中文文件名原样输出；Windows 下显式按 UTF-8 解码，
    # 否则默认代码页与引号转义会把顶层中文文件名解析成伪目录（如 '"docs'）。
    out = subprocess.run(
        ["git", "-c", "core.quotepath=off", "ls-files"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout
    return [line for line in out.splitlines() if line.strip()]


def test_frozen_directories_exist() -> None:
    for rel in FROZEN_DIRS:
        assert (REPO_ROOT / rel).is_dir(), f"缺少冻结目录：{rel}"


def test_exactly_three_business_modules() -> None:
    modules = REPO_ROOT / "backend" / "app" / "modules"
    # __pycache__ 是运行字节码缓存，不是业务模块；任何模块被导入后都会出现。
    actual = {
        p.name for p in modules.iterdir() if p.is_dir() and p.name != "__pycache__"
    }
    assert actual == MODULE_DIRS, "不得建立第五个业务模块"


def test_no_catch_all_utility_directories() -> None:
    banned_parts = {"common", "utils", "shared"}
    for path in git_tracked():
        parts = set(Path(path).parts)
        assert not parts & banned_parts, f"禁止出现通用杂物目录：{path}"


def test_top_level_boundary() -> None:
    top_dirs: set[str] = set()
    top_files: set[str] = set()
    for path in git_tracked():
        top = Path(path).parts[0]
        if len(Path(path).parts) > 1:
            top_dirs.add(top)
        else:
            top_files.add(top)
    assert top_dirs <= ALLOWED_TOP_LEVEL_DIRS, top_dirs - ALLOWED_TOP_LEVEL_DIRS
    assert top_files <= ALLOWED_TOP_LEVEL_FILES, top_files - ALLOWED_TOP_LEVEL_FILES


def test_four_powershell_entries_exist() -> None:
    for name in SCRIPTS:
        assert (REPO_ROOT / "scripts" / name).is_file(), f"缺少脚本：scripts/{name}"


def test_dependency_lock_exists() -> None:
    lock = REPO_ROOT / "uv.lock"
    assert lock.is_file() and lock.stat().st_size > 0, "缺少 uv.lock 依赖锁定基础"


def test_gitignore_covers_runtime_and_secrets() -> None:
    for rel in ("runtime_data/x.db", "source_data/ecommercedata-main/README.md", ".env"):
        result = subprocess.run(
            ["git", "check-ignore", "-q", rel],
            cwd=REPO_ROOT,
        )
        assert result.returncode == 0, f".gitignore 未忽略：{rel}"


def test_registry_covers_all_37_tasks() -> None:
    registry = json.loads((REPO_ROOT / "config" / "test_tasks.json").read_text("utf-8"))
    expected = {f"M1-{i:02d}" for i in range(1, 10)}
    expected |= {f"M2-{i:02d}" for i in range(1, 11)}
    expected |= {f"M3-{i:02d}" for i in range(1, 10)}
    expected |= {f"M4-{i:02d}" for i in range(1, 10)}
    assert set(registry["tasks"]) == expected
    assert set(registry["modules"]) == {"M1", "M2", "M3", "M4"}
