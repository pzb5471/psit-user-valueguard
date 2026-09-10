"""同源 SPA 托管不得遮蔽 API 与静态资源的 404。"""

from fastapi.testclient import TestClient

from app.modules.application.api.router import create_contract_app
from app.modules.application.static_frontend import mount_frontend


def test_spa_fallback_only_handles_frontend_routes(tmp_path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text('<div id="root"></div>', encoding="utf-8")
    app = create_contract_app()
    mount_frontend(app, dist)

    with TestClient(app) as client:
        assert client.get("/batches/demo").status_code == 200
        assert client.get("/api/v1/not-found").status_code == 404
        assert client.get("/assets/not-found.js").status_code == 404
