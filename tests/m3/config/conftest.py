"""M3-02 测试共用夹具：一份与 config/default.toml 一致的最小合法配置。"""

from __future__ import annotations

from typing import Any

import pytest


@pytest.fixture()
def base_config() -> dict[str, Any]:
    return {
        "http": {"host": "127.0.0.1", "port": 8000},
        "frontend": {"dev_port": 5173},
        "storage": {"runtime_dir": "runtime_data"},
        "analysis": {
            "production_enabled": False,
            "connect_timeout_seconds": 10,
            "response_timeout_seconds": 300,
            "max_tokens": 4096,
        },
        "retry": {"max_attempts": 3},
        "executor": {"case_concurrency": 2},
        "polling": {"active_batch_interval_seconds": 2},
        "logging": {"level": "INFO"},
    }
