"""统一测试入口的参数校验行为（M3-01 自动验收：脚本参数）。"""

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
TEST_PS1 = REPO_ROOT / "scripts" / "test.ps1"


def run_dispatcher(*args: str) -> subprocess.CompletedProcess:
    command = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(TEST_PS1),
        *args,
    ]
    # powershell.exe 的输出使用系统 ANSI 代码页；用替换模式解码，断言只依赖 ASCII 内容。
    return subprocess.run(
        command,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def test_unknown_task_id_is_rejected() -> None:
    result = run_dispatcher("-Task", "M9-99")
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "M3-01" in combined, "错误信息应列出已注册的 Task ID"


def test_task_and_module_are_mutually_exclusive() -> None:
    result = run_dispatcher("-Task", "M3-01", "-Module", "M3")
    assert result.returncode != 0


def test_invalid_module_is_rejected() -> None:
    result = run_dispatcher("-Module", "M5")
    assert result.returncode != 0
