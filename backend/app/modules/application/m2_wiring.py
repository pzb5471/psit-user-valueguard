"""M3-09 真实 M2 装配：AnalysisEngine + 可注入模型客户端（规格第 9、14 节）。

把 Fake M2 替换为真实 AnalysisEngine。模型客户端按边界注入：确定性验收与
E2E 使用 ScriptedGlmClient（零网络模型调用）；真实 GlmClient 待 M2-10 PoC
冻结参数后在启动入口启用，本装配层不区分两者（同一 AnalysisModelClient
协议）。动作目录从 config/action_catalog.v1.json 同源加载。
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from app.contracts.data import CaseInput
from app.modules.analysis.client import GlmCallParams
from app.modules.analysis.client.client import AnalysisModelClient
from app.modules.analysis.engine.engine import AnalysisEngine
from app.modules.analysis.strategy.input_builder import (
    ActionCatalogEntry,
    ActionCatalogView,
)

ImageResolver = Callable[[str], tuple[str, bytes]]
CaseImageResolver = Callable[[CaseInput, str], tuple[str, bytes]]


def _missing_image_resolver(_asset_relative_path: str) -> tuple[str, bytes]:
    raise RuntimeError("案例含图片但未提供 image_data_resolver（M3 装配层）")


def load_action_catalog() -> ActionCatalogView:
    """从 config/action_catalog.v1.json 构造动作目录视图（M2 装配约定）。"""
    root = Path(__file__).resolve()
    for candidate in root.parents:
        catalog = candidate / "config" / "action_catalog.v1.json"
        if catalog.is_file():
            data = json.loads(catalog.read_text(encoding="utf-8"))
            return ActionCatalogView(
                catalog_version=str(data["catalog_version"]),
                actions=tuple(
                    ActionCatalogEntry(
                        action_type=str(item["action_type"]),
                        description=str(item["description"]),
                    )
                    for item in data["actions"]
                ),
            )
    raise FileNotFoundError("未找到 config/action_catalog.v1.json")


def build_analysis_engine(
    model_client: AnalysisModelClient,
    *,
    image_data_resolver: ImageResolver | None = None,
    case_image_data_resolver: CaseImageResolver | None = None,
    connect_timeout_seconds: float = 10.0,
    response_timeout_seconds: float = 300.0,
    params: GlmCallParams | None = None,
) -> AnalysisEngine:
    """构造真实 M2 引擎；图片字节由装配方按 asset_relative_path 提供。"""
    return AnalysisEngine(
        model_client=model_client,
        image_data_resolver=image_data_resolver or _missing_image_resolver,
        case_image_data_resolver=case_image_data_resolver,
        action_catalog=load_action_catalog(),
        connect_timeout_seconds=connect_timeout_seconds,
        response_timeout_seconds=response_timeout_seconds,
        params=params,
    )
