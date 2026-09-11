"""开发环境双进程入口：统一配置启动 FastAPI 与 Vite。"""

from __future__ import annotations

import argparse
import os
import shutil
import signal
import subprocess
import sys
import time

from app.modules.application.app_factory import PortInUseError, ensure_port_available
from app.modules.application.config.settings import Settings, find_project_root


class DevToolMissingError(RuntimeError):
    """The checked-in development entry cannot run with local dependencies."""


def build_vite_command(
    *,
    repo_root: os.PathLike[str],
    node_executable: str,
    host: str,
    port: int,
) -> list[str]:
    vite_cli = os.path.join(
        os.fspath(repo_root),
        "frontend",
        "node_modules",
        "vite",
        "bin",
        "vite.js",
    )
    if not os.path.isfile(vite_cli):
        raise DevToolMissingError(
            "DEV_TOOL_MISSING: frontend dependencies are not installed; "
            "run scripts/bootstrap.ps1"
        )
    return [
        node_executable,
        vite_cli,
        "--host",
        host,
        "--port",
        str(port),
        "--strictPort",
    ]


def _stop(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    try:
        if sys.platform == "win32":
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            process.terminate()
        process.wait(timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def _run(check_only: bool) -> int:
    settings = Settings.load()
    ensure_port_available(settings.http.host, settings.http.port)
    ensure_port_available(settings.http.host, settings.frontend.dev_port)
    node = shutil.which("node")
    if node is None:
        raise DevToolMissingError("DEV_TOOL_MISSING: node is not available on PATH")
    repo_root = find_project_root()
    vite_command = build_vite_command(
        repo_root=repo_root,
        node_executable=node,
        host=settings.http.host,
        port=settings.frontend.dev_port,
    )
    if check_only:
        print(
            f"[PASS] DEV_CONFIG_READY: API {settings.http.host}:{settings.http.port}; "
            f"Vite {settings.http.host}:{settings.frontend.dev_port}"
        )
        return 0

    env = os.environ.copy()
    env["VITE_API_ORIGIN"] = f"http://{settings.http.host}:{settings.http.port}"
    creationflags = (
        subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
    )
    backend = subprocess.Popen(
        [sys.executable, "-m", "app.modules.application.launcher"],
        cwd=repo_root,
        env=env,
        creationflags=creationflags,
    )
    frontend = subprocess.Popen(
        vite_command,
        cwd=repo_root / "frontend",
        env=env,
        creationflags=creationflags,
    )
    try:
        while True:
            backend_exit = backend.poll()
            frontend_exit = frontend.poll()
            if backend_exit is not None:
                return backend_exit
            if frontend_exit is not None:
                return frontend_exit
            time.sleep(0.2)
    except KeyboardInterrupt:
        return 0
    finally:
        _stop(frontend)
        _stop(backend)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Start the PSIT API and Vite dev server")
    parser.add_argument("--check", action="store_true", help="validate tools and ports only")
    args = parser.parse_args(argv)
    try:
        return _run(args.check)
    except PortInUseError as error:
        print(error, file=sys.stderr)
        return 3
    except DevToolMissingError as error:
        print(error, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
