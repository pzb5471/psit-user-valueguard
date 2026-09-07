"""M2-02 验收：Prompt 加载、Schema 注入、版本与 SHA-256 清单（规格第 7、9.2、9.4 节）。

面向公开接口验证：load_stage_prompt / load_prompt_manifest 只消费 M2-01 冻结的
Pydantic 合同生成唯一 JSON Schema，不复制第二份字段表；模板缺文件必须失败。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest

from app.contracts.analysis import (
    AnalysisStage,
    AttributionResult,
    DecisionPackage,
    PerceptionResult,
)
from app.modules.analysis.prompts import (
    PROMPT_VERSIONS,
    load_prompt_manifest,
    load_stage_prompt,
)
from app.modules.analysis.prompts.loader import (
    _RESPONSE_SCHEMA_PLACEHOLDER,
    TEMPLATE_NAMES,
)

pytestmark = pytest.mark.task_m2_02

STAGES = tuple(AnalysisStage)

STAGE_RESULT_MODELS = {
    AnalysisStage.PERCEPTION: PerceptionResult,
    AnalysisStage.ATTRIBUTION: AttributionResult,
    AnalysisStage.STRATEGY: DecisionPackage,
}


def _expected_schema(stage: AnalysisStage) -> dict[str, Any]:
    """独立真源：测试侧直接从 M2-01 合同模型生成 Schema，与实现无共享代码。"""
    return STAGE_RESULT_MODELS[stage].model_json_schema()


class TestStagePromptLoading:
    """三阶段 Prompt 从包内模板文件加载，版本冻结为 v1。"""

    @pytest.mark.parametrize("stage", STAGES)
    def test_load_returns_v1_prompt_for_each_stage(self, stage: AnalysisStage) -> None:
        prompt = load_stage_prompt(stage)

        assert prompt.stage == stage
        assert prompt.version == "v1"
        assert prompt.template_name == TEMPLATE_NAMES[stage]
        assert prompt.template_name.endswith(".v1.md")
        assert PROMPT_VERSIONS[stage] == "v1"

    @pytest.mark.parametrize("stage", STAGES)
    def test_rendered_prompt_injects_contract_schema(self, stage: AnalysisStage) -> None:
        """Schema 注入：渲染文本必须内嵌从 Pydantic 合同生成的唯一 Schema。"""
        prompt = load_stage_prompt(stage)

        embedded = json.dumps(
            prompt.response_schema, ensure_ascii=False, indent=2, sort_keys=True
        )
        assert embedded in prompt.rendered_text
        assert prompt.response_schema == _expected_schema(stage)

    @pytest.mark.parametrize("stage", STAGES)
    def test_template_carries_single_schema_placeholder(self, stage: AnalysisStage) -> None:
        """模板只保留一个 Schema 注入占位符，渲染后不得残留占位符。"""
        from app.modules.analysis.prompts.loader import _template_path

        template_text = _template_path(stage).read_text(encoding="utf-8")
        assert template_text.count(_RESPONSE_SCHEMA_PLACEHOLDER) == 1

        prompt = load_stage_prompt(stage)
        assert _RESPONSE_SCHEMA_PLACEHOLDER not in prompt.rendered_text


class TestPromptManifest:
    """版本与 SHA-256 清单：每次调用记录 Prompt 版本与渲染文本指纹。"""

    @pytest.mark.parametrize("stage", STAGES)
    def test_manifest_records_version_and_rendered_hash(self, stage: AnalysisStage) -> None:
        prompt = load_stage_prompt(stage)
        manifest = load_prompt_manifest()
        entry = manifest[stage]

        expected_sha = hashlib.sha256(prompt.rendered_text.encode("utf-8")).hexdigest()
        assert entry.version == "v1"
        assert entry.sha256 == expected_sha
        assert entry.sha256 == prompt.sha256
        assert entry.template_name == TEMPLATE_NAMES[stage]

    def test_manifest_covers_exactly_three_stages(self) -> None:
        manifest = load_prompt_manifest()
        assert set(manifest) == set(STAGES)


class TestPromptHashSensitivity:
    """哈希变化：模板内容任何变化都必须改变渲染文本的 SHA-256 指纹。"""

    def test_tampered_template_changes_sha256(self, tmp_path, monkeypatch) -> None:
        from app.modules.analysis.prompts import loader

        stage = AnalysisStage.PERCEPTION
        baseline = load_stage_prompt(stage)

        original = loader._template_path(stage)
        tampered = tmp_path / TEMPLATE_NAMES[stage]
        tampered.write_text(
            original.read_text(encoding="utf-8") + "\n<!-- 修订一笔 -->\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(loader, "PROMPTS_DIR", tmp_path)

        prompt = load_stage_prompt(stage)

        assert prompt.sha256 != baseline.sha256
        assert prompt.rendered_text != baseline.rendered_text


class TestMissingTemplateFails:
    """缺文件失败：模板缺失或占位符缺失时加载必须报错，不得静默降级。"""

    def test_missing_template_file_raises(self, tmp_path, monkeypatch) -> None:
        from app.modules.analysis.prompts import loader

        monkeypatch.setattr(loader, "PROMPTS_DIR", tmp_path)
        with pytest.raises(FileNotFoundError):
            load_stage_prompt(AnalysisStage.PERCEPTION)

    def test_template_without_placeholder_is_rejected(self, tmp_path, monkeypatch) -> None:
        from app.modules.analysis.prompts import loader

        stage = AnalysisStage.PERCEPTION
        broken = tmp_path / TEMPLATE_NAMES[stage]
        broken.write_text("没有占位符的模板", encoding="utf-8")
        monkeypatch.setattr(loader, "PROMPTS_DIR", tmp_path)

        with pytest.raises(ValueError, match="占位符"):
            load_stage_prompt(stage)

    def test_manifest_missing_template_raises(self, tmp_path, monkeypatch) -> None:
        from app.modules.analysis.prompts import loader

        monkeypatch.setattr(loader, "PROMPTS_DIR", tmp_path)
        with pytest.raises(FileNotFoundError):
            load_prompt_manifest()
