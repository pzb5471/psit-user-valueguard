"""M3-05 传给 M2 AnalysisRequest 的版本集合。

版本值由 M2 合同/Prompt 冻结；M3 仅显式注入并转发，不在运行服务内推断或改写。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AnalysisVersionConfig:
    perception_contract_version: str
    attribution_contract_version: str
    strategy_contract_version: str
    perception_prompt_version: str
    attribution_prompt_version: str
    strategy_prompt_version: str
    action_catalog_version: str
