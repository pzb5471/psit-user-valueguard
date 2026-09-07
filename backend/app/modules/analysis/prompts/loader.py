"""M2-02 Prompt 加载器：模板加载、Schema 注入、版本与 SHA-256 清单（规格第 9.2 节）。

三份 v1 Prompt 模板与阶段结果 Schema 同仓存放；渲染文本 = 模板注入唯一合同 Schema。
load_prompt_manifest 提供每阶段 Prompt 版本与渲染文本 SHA-256，供 M2-03、M2-08
记录 Prompt 版本与请求清单使用；模板或合同任何变化都会改变指纹。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.contracts.analysis import AnalysisStage
from app.modules.analysis.prompts.schemas import response_schema_for

PROMPTS_DIR = Path(__file__).resolve().parent

_RESPONSE_SCHEMA_PLACEHOLDER = "{{RESPONSE_JSON_SCHEMA}}"

TEMPLATE_NAMES: dict[AnalysisStage, str] = {
    AnalysisStage.PERCEPTION: "perception.v1.md",
    AnalysisStage.ATTRIBUTION: "attribution.v1.md",
    AnalysisStage.STRATEGY: "strategy.v1.md",
}

PROMPT_VERSIONS: dict[AnalysisStage, str] = {stage: "v1" for stage in TEMPLATE_NAMES}


@dataclass(frozen=True)
class StagePrompt:
    """单个阶段的最终 Prompt：模板文本、注入的合同 Schema 与渲染结果指纹。"""

    stage: AnalysisStage
    version: str
    template_name: str
    template_text: str
    response_schema: dict[str, Any]
    rendered_text: str
    sha256: str


@dataclass(frozen=True)
class PromptManifestEntry:
    """清单条目：Prompt 版本与渲染文本 SHA-256（AnalysisRequest 的 Prompt 版本来源）。"""

    stage: AnalysisStage
    version: str
    template_name: str
    sha256: str


def _template_path(stage: AnalysisStage, prompts_dir: Path | None = None) -> Path:
    directory = PROMPTS_DIR if prompts_dir is None else prompts_dir
    return directory / TEMPLATE_NAMES[stage]


def _load_template(stage: AnalysisStage, prompts_dir: Path | None = None) -> str:
    path = _template_path(stage, prompts_dir)
    if not path.is_file():
        raise FileNotFoundError(f"缺少 {stage.value} 阶段 Prompt 模板：{path.name}")
    return path.read_text(encoding="utf-8")


def _render_schema(schema: dict[str, Any]) -> str:
    return json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True)


def load_stage_prompt(
    stage: AnalysisStage, prompts_dir: Path | None = None
) -> StagePrompt:
    """加载并渲染一个阶段的 Prompt；模板缺失、占位符缺失或版本不一致时立即失败。"""
    stage_key = AnalysisStage(stage)
    template_name = TEMPLATE_NAMES[stage_key]
    template_text = _load_template(stage_key, prompts_dir)
    if template_text.count(_RESPONSE_SCHEMA_PLACEHOLDER) != 1:
        raise ValueError(
            f"{template_name} 必须包含且只包含一个 {_RESPONSE_SCHEMA_PLACEHOLDER} 占位符"
        )
    template_version = template_name.split(".")[1]
    if template_version != PROMPT_VERSIONS[stage_key]:
        raise ValueError(
            f"{template_name} 的版本 {template_version} 与 PROMPT_VERSIONS 的"
            f" {PROMPT_VERSIONS[stage_key]} 不一致"
        )
    schema = response_schema_for(stage_key)
    rendered_text = template_text.replace(
        _RESPONSE_SCHEMA_PLACEHOLDER, _render_schema(schema)
    )
    return StagePrompt(
        stage=stage_key,
        version=PROMPT_VERSIONS[stage_key],
        template_name=template_name,
        template_text=template_text,
        response_schema=schema,
        rendered_text=rendered_text,
        sha256=hashlib.sha256(rendered_text.encode("utf-8")).hexdigest(),
    )


def load_prompt_manifest(
    prompts_dir: Path | None = None,
) -> dict[AnalysisStage, PromptManifestEntry]:
    """三阶段版本与 SHA-256 清单；任一模板或合同变化都会改变指纹。"""
    manifest: dict[AnalysisStage, PromptManifestEntry] = {}
    for stage in TEMPLATE_NAMES:
        prompt = load_stage_prompt(stage, prompts_dir)
        manifest[stage] = PromptManifestEntry(
            stage=stage,
            version=prompt.version,
            template_name=prompt.template_name,
            sha256=prompt.sha256,
        )
    return manifest
