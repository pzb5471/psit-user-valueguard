"""重新生成 OpenAPI 快照（合同有意变更时使用，见 test_openapi_snapshot 模块注释）。"""

from __future__ import annotations

import json
from pathlib import Path

from app.modules.application.api.router import create_contract_app

SNAPSHOT = Path(__file__).resolve().parent / "openapi_snapshot.json"


def main() -> None:
    schema = create_contract_app().openapi()
    SNAPSHOT.write_text(
        json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"已重新生成 {SNAPSHOT}")


if __name__ == "__main__":
    main()
