"""同源托管已构建的 React 前端，并支持浏览器刷新深层路由。"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response
from starlette.types import Scope


class SpaStaticFiles(StaticFiles):
    """SPA 路由回退 index.html，但不吞掉 API 或带后缀的静态资源 404。"""

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as error:
            normalized_path = str(scope.get("path", "")).lstrip("/")
            is_frontend_route = not normalized_path.startswith(
                ("api/", "e2e/")
            ) and not Path(normalized_path).suffix
            if error.status_code != 404 or not is_frontend_route:
                raise
            return await super().get_response("index.html", scope)


def mount_frontend(app: FastAPI, dist_dir: Path) -> None:
    """在 API 路由注册后挂载前端兜底；缺少构建产物时立即失败。"""
    if not (dist_dir / "index.html").is_file():
        raise FileNotFoundError(f"未找到前端构建产物：{dist_dir / 'index.html'}")
    app.mount("/", SpaStaticFiles(directory=str(dist_dir), html=True), name="frontend")
