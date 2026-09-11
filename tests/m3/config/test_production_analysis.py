"""生产分析装配回归：密钥、显式开关与真实客户端必须同时满足。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from app.contracts.data import CaseInput
from app.modules.application.app_factory import PortInUseError
from app.modules.application.config.settings import Settings
from app.modules.application.production_analysis import (
    build_production_analysis,
    create_runtime_image_resolver,
)


def _settings(base_config: dict[str, Any], *, enabled: bool, key: str | None) -> Settings:
    config = {
        **base_config,
        "analysis": {**base_config["analysis"], "production_enabled": enabled},
    }
    return Settings.model_validate({**config, "ZAI_API_KEY": key})


def test_missing_key_keeps_analysis_closed(base_config: dict[str, Any]) -> None:
    binding = build_production_analysis(_settings(base_config, enabled=True, key=None))

    assert binding.available is False
    assert binding.health.health_check() is False
    assert "ZAI_API_KEY" in binding.message


def test_key_without_production_gate_keeps_analysis_closed(
    base_config: dict[str, Any],
) -> None:
    binding = build_production_analysis(
        _settings(base_config, enabled=False, key="fake-key-not-real")
    )

    assert binding.available is False
    assert binding.health.health_check() is False
    assert "未开放真实分析" in binding.message


def test_enabled_binding_constructs_real_client_with_frozen_settings(
    base_config: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.modules.application import production_analysis

    captured: dict[str, Any] = {}
    fake_engine = object()

    class CapturingClient:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

    def fake_build(client: object, **kwargs: Any) -> object:
        captured["client"] = client
        captured.update(kwargs)
        return fake_engine

    monkeypatch.setattr(production_analysis, "GlmClient", CapturingClient)
    monkeypatch.setattr(production_analysis, "build_analysis_engine", fake_build)

    binding = build_production_analysis(
        _settings(base_config, enabled=True, key="fake-key-not-real"),
        runtime_root=Path("runtime_data"),
    )

    assert binding.available is True
    assert binding.engine is fake_engine
    assert binding.health.health_check() is True
    assert captured["api_key"] == "fake-key-not-real"
    assert captured["connect_timeout_seconds"] == 10
    assert captured["response_timeout_seconds"] == 300
    assert captured["params"].max_tokens == 4096
    assert callable(captured["case_image_data_resolver"])


def test_runtime_image_resolver_is_case_scoped_and_hash_checked(tmp_path: Path) -> None:
    fixture = (
        Path(__file__).resolve().parents[2]
        / "fixtures"
        / "runtime"
        / "contracts"
        / "valid_case_input.json"
    )
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    image_bytes = b"\x89PNG\r\n\x1a\nfixture"
    image_path = f"assets/{payload['case_id']}/evidence.png"
    payload["evidence"]["image_items"] = [
        {
            "evidence_id": "img-0001",
            "identity": "observed",
            "relation_identity": "mock_mapped",
            "source_ref": {
                "dataset": "fixture",
                "relative_path": "images/evidence.png",
                "record_key": "img-0001",
                "field": "image",
            },
            "content_hash": hashlib.sha256(image_bytes).hexdigest(),
            "asset_relative_path": image_path,
            "media_type": "image/png",
        }
    ]
    case = CaseInput.model_validate(payload)
    target = tmp_path / "batches" / case.batch_id / case.data_version / image_path
    target.parent.mkdir(parents=True)
    target.write_bytes(image_bytes)

    resolver = create_runtime_image_resolver(tmp_path)
    assert resolver(case, image_path) == ("image/png", image_bytes)

    target.write_bytes(image_bytes + b"tampered")
    with pytest.raises(OSError, match="校验值"):
        resolver(case, image_path)


def test_launcher_checks_port_before_touching_runtime(
    base_config: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.modules.application import launcher

    settings = _settings(base_config, enabled=False, key=None)
    touched_runtime = False

    def occupied(_host: str, _port: int) -> None:
        raise PortInUseError("PORT_IN_USE: occupied")

    def unexpected_runtime(_path: Path) -> object:
        nonlocal touched_runtime
        touched_runtime = True
        return object()

    monkeypatch.setattr(launcher.Settings, "load", lambda: settings)
    monkeypatch.setattr(launcher, "ensure_port_available", occupied)
    monkeypatch.setattr(launcher, "build_runtime", unexpected_runtime)

    with pytest.raises(PortInUseError, match="PORT_IN_USE"):
        launcher.run()
    assert touched_runtime is False


def test_launcher_main_maps_port_conflict_to_stable_exit(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from app.modules.application import launcher

    def occupied_run() -> None:
        raise PortInUseError("PORT_IN_USE: occupied")

    monkeypatch.setattr(launcher, "run", occupied_run)

    assert launcher.main() == 3
    assert "PORT_IN_USE: occupied" in capsys.readouterr().err
