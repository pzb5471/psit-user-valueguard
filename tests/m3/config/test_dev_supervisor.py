from pathlib import Path

import pytest

from app.modules.application.dev_supervisor import (
    DevToolMissingError,
    build_vite_command,
)


def test_vite_command_uses_configured_host_and_port_without_pnpm_separator(
    tmp_path: Path,
) -> None:
    vite_cli = tmp_path / "frontend" / "node_modules" / "vite" / "bin" / "vite.js"
    vite_cli.parent.mkdir(parents=True)
    vite_cli.write_text("", encoding="utf-8")

    command = build_vite_command(
        repo_root=tmp_path,
        node_executable="C:/tools/node.exe",
        host="127.0.0.1",
        port=15173,
    )

    assert command == [
        "C:/tools/node.exe",
        str(vite_cli),
        "--host",
        "127.0.0.1",
        "--port",
        "15173",
        "--strictPort",
    ]
    assert "--" not in command


def test_vite_command_fails_clearly_when_local_entry_is_missing(tmp_path: Path) -> None:
    with pytest.raises(DevToolMissingError, match="frontend dependencies"):
        build_vite_command(
            repo_root=tmp_path,
            node_executable="C:/tools/node.exe",
            host="127.0.0.1",
            port=15173,
        )
