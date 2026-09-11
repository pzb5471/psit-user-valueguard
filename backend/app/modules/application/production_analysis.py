"""生产 GLM 装配门禁与运行案例图片解析。"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from app.contracts.analysis import AnalysisEventSink, AnalysisOutcome, AnalysisRequest
from app.contracts.data import CaseInput
from app.modules.analysis.client import GlmCallParams, GlmClient
from app.modules.application.config.settings import Settings
from app.modules.application.m2_wiring import build_analysis_engine
from app.modules.application.run_service.ports import AnalysisEnginePort


class _UnavailableAnalysis:
    def __init__(self, message: str) -> None:
        self._message = message

    def analyze_case(
        self, request: AnalysisRequest, event_sink: AnalysisEventSink
    ) -> AnalysisOutcome:
        raise RuntimeError(self._message)

    def close(self) -> None:
        return None


class _StaticAnalysisHealth:
    def __init__(self, *, available: bool, message: str) -> None:
        self._available = available
        self._message = message

    def health_check(self) -> bool:
        return self._available

    def health_message(self) -> str:
        return self._message


@dataclass(frozen=True, slots=True)
class ProductionAnalysisBinding:
    engine: AnalysisEnginePort
    health: _StaticAnalysisHealth
    available: bool
    message: str


def create_runtime_image_resolver(runtime_root: Path):
    """按 CaseInput 的批次和数据版本读取当前案例图片，并复核内容哈希。"""

    root = Path(runtime_root).resolve()

    def resolve(case: CaseInput, asset_relative_path: str) -> tuple[str, bytes]:
        package_root = (root / "batches" / case.batch_id / case.data_version).resolve()
        if not package_root.is_relative_to(root):
            raise OSError("案例包目录越出运行数据根目录")
        target = package_root.joinpath(*PurePosixPath(asset_relative_path).parts).resolve()
        if not target.is_relative_to(package_root):
            raise OSError("图片路径越出当前案例包目录")

        matches = [
            item
            for item in case.evidence.image_items
            if item.asset_relative_path == asset_relative_path
        ]
        if len(matches) != 1:
            raise FileNotFoundError("当前案例不存在对应图片证据")
        image = matches[0]
        data = target.read_bytes()
        if hashlib.sha256(data).hexdigest() != image.content_hash:
            raise OSError("图片内容校验值与 CaseInput 不一致")
        return image.media_type.value, data

    return resolve


def build_production_analysis(
    settings: Settings,
    *,
    runtime_root: Path | None = None,
) -> ProductionAnalysisBinding:
    """只有密钥与显式 PoC 门禁同时满足时才装配真实 GlmClient。"""

    if settings.zai_api_key is None:
        message = "未配置 ZAI_API_KEY，分析不可用；历史结果仍可查看"
        unavailable = _UnavailableAnalysis(message)
        return ProductionAnalysisBinding(
            engine=unavailable,
            health=_StaticAnalysisHealth(available=False, message=message),
            available=False,
            message=message,
        )

    if not settings.analysis.production_enabled:
        message = "已配置 ZAI_API_KEY，但 M2-10 真实 GLM PoC 与双人验收尚未开放生产分析"
        unavailable = _UnavailableAnalysis(message)
        return ProductionAnalysisBinding(
            engine=unavailable,
            health=_StaticAnalysisHealth(available=False, message=message),
            available=False,
            message=message,
        )

    if runtime_root is None:
        raise ValueError("启用生产分析时必须提供 runtime_root")

    params = GlmCallParams(max_tokens=settings.analysis.max_tokens)
    client = GlmClient(
        api_key=settings.zai_api_key.get_secret_value(),
        connect_timeout_seconds=settings.analysis.connect_timeout_seconds,
        response_timeout_seconds=settings.analysis.response_timeout_seconds,
        params=params,
    )
    engine = build_analysis_engine(
        client,
        case_image_data_resolver=create_runtime_image_resolver(runtime_root),
        connect_timeout_seconds=settings.analysis.connect_timeout_seconds,
        response_timeout_seconds=settings.analysis.response_timeout_seconds,
        params=params,
    )
    message = "真实分析引擎已按 M2-10 验收门禁启用"
    return ProductionAnalysisBinding(
        engine=engine,
        health=_StaticAnalysisHealth(available=True, message=message),
        available=True,
        message=message,
    )
