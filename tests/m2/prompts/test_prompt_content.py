"""M2-02 验收：Prompt 内容边界（规格第 7.1、9.2 节）。

按阶段最小权限表扫描三份 v1 Prompt 模板：密封答案字段名、凭据与运行环境痕迹、
越权阶段内容必须逐项缺失，职责词句与受控词表必须存在；v1 模板指纹快照保证
内容未被无意修改，有意修订时必须随人工验收同步更新快照常量。
"""

from __future__ import annotations

import hashlib

import pytest

from app.contracts.analysis import AnalysisStage
from app.modules.analysis.prompts.loader import _template_path

pytestmark = pytest.mark.task_m2_02

STAGES = ("PERCEPTION", "ATTRIBUTION", "STRATEGY")

# 规格第 4、6 节：service_tasks.json 的密封验收材料字段名，不得进入任何 Prompt。
SEALED_ANSWER_TOKENS = (
    "key_answer",
    "database_gt",
    "user_profile",
    "user_profile_st1",
    "question_type",
    "trajectory",
)

# 凭据与本机运行环境痕迹，不得出现在任何 Prompt。
SECRET_AND_ENVIRONMENT_TOKENS = (
    "api_key",
    "API_KEY",
    "sk-",
    "Authorization",
    "Bearer ",
    "C:\\",
    "E:\\",
    "/Users/",
)

# 规格第 9.2 节：动作目录与介入等级只允许策略阶段读取。
STRATEGY_ONLY_TOKENS = (
    "action_catalog",
    "动作目录",
    "EVIDENCE_CHECK",
    "CUSTOMER_CONTACT",
    "FULFILLMENT_ESCALATION",
    "REPLACEMENT_RETURN_REFUND_CHECK",
    "APOLOGY_COMPENSATION_RETENTION_REQUEST",
    "NO_ACTION_MONITOR",
    "intervention_level",
    "MUST_INTERVENE",
    "SHOULD_INTERVENE",
    "NO_IMMEDIATE_INTERVENTION",
)

# 高价值结论、RFM 与决策包是策略阶段输入；感知与归因不得出现。
ATTRIBUTION_AND_PERCEPTION_TOKENS = STRATEGY_ONLY_TOKENS + (
    "高价值",
    "RFM",
    "DecisionPackage",
)

# 业务原因枚举与证据不足兜底只允许归因阶段使用；感知不得出现。
ATTRIBUTION_ONLY_TOKENS = (
    "INSUFFICIENT_EVIDENCE",
    "LOGISTICS_FULFILLMENT",
    "PRODUCT_ISSUE",
    "RETURN_REFUND",
    "SERVICE_COMMUNICATION",
    "PRICE_OR_BENEFIT",
    "AttributionResult",
)

FORBIDDEN_TOKENS_BY_STAGE: dict[str, tuple[str, ...]] = {
    "PERCEPTION": ATTRIBUTION_AND_PERCEPTION_TOKENS + ATTRIBUTION_ONLY_TOKENS,
    "ATTRIBUTION": ATTRIBUTION_AND_PERCEPTION_TOKENS,
    "STRATEGY": ("RFM",),
}

REQUIRED_CONTENT_BY_STAGE: dict[str, tuple[str, ...]] = {
    "PERCEPTION": (
        "感知阶段",
        "不做原因判断，不做处理建议",
        "CUSTOMER_CLAIMED",
        "SERVICE_AGENT_STATED_OR_PROMISED",
        "CUSTOMER_CONFIRMED",
        "IMAGE_DIRECT_OBSERVATION",
        "PROGRAM_DERIVED",
        "UNRESOLVED",
        "UNCONFIRMABLE",
        "UNKNOWN",
        "MUTUALLY_SUPPORTS",
        "CONFLICTS_WITH",
        "SUPPLEMENTS",
        "UNDETERMINED",
        "CALM",
        "IMPATIENT",
        "不得从客户文本反推图片内容",
        "不得根据客服语气推断客户情绪",
        "missing_evidence",
    ),
    "ATTRIBUTION": (
        "归因阶段",
        "不做处理建议",
        "LOGISTICS_FULFILLMENT",
        "PRODUCT_ISSUE",
        "RETURN_REFUND",
        "SERVICE_COMMUNICATION",
        "PRICE_OR_BENEFIT",
        "OTHER",
        "INSUFFICIENT_EVIDENCE",
        "alternative_cause",
        "counter_evidence_ids",
        "不得写成已经证明的因果事实",
        "不得并入 OTHER",
    ),
    "STRATEGY": (
        "策略阶段",
        "高价值客户结论",
        "EVIDENCE_CHECK",
        "CUSTOMER_CONTACT",
        "FULFILLMENT_ESCALATION",
        "REPLACEMENT_RETURN_REFUND_CHECK",
        "APOLOGY_COMPENSATION_RETENTION_REQUEST",
        "NO_ACTION_MONITOR",
        "MUST_INTERVENE",
        "SHOULD_INTERVENE",
        "NO_IMMEDIATE_INTERVENTION",
        "最低介入规则",
        "不得生成具体补偿金额、权益承诺、退款完成状态或任何真实执行结果",
        "高价值客户身份本身不得单独触发 MUST_INTERVENE",
    ),
}

# v1 模板指纹快照（SHA-256，UTF-8 原文）。有意修订 Prompt 时必须提升版本号、
# 同步 loader.PROMPT_VERSIONS，并在人工验收通过后更新本快照。
V1_TEMPLATE_SHA256 = {
    "PERCEPTION": "1ce577851b61291e2e4a8177f28073c1159567c212b6c5631317c029486939af",
    "ATTRIBUTION": "603cdee68bdc6ee4e9c9e47a3d68609097290bed2ef5e3c541872166fcb86fcf",
    "STRATEGY": "49169987e6e2d421b4c3402021a526b640233b10f84af9d18020f32615810911",
}


def _template_text(stage: str) -> str:
    return _template_path(AnalysisStage(stage)).read_text(encoding="utf-8")


class TestStageMinimalPermission:
    """规格第 9.2 节阶段最小权限：Prompt 模板不得包含未获准内容。"""

    @pytest.mark.parametrize("stage", STAGES)
    def test_no_sealed_answer_fields(self, stage: str) -> None:
        template_text = _template_text(stage)
        for token in SEALED_ANSWER_TOKENS:
            assert token not in template_text, f"{stage} 模板出现密封答案字段：{token}"

    @pytest.mark.parametrize("stage", STAGES)
    def test_no_secrets_or_environment_paths(self, stage: str) -> None:
        template_text = _template_text(stage)
        for token in SECRET_AND_ENVIRONMENT_TOKENS:
            assert token not in template_text, f"{stage} 模板出现禁止内容：{token}"

    @pytest.mark.parametrize("stage", STAGES)
    def test_no_out_of_permission_content(self, stage: str) -> None:
        template_text = _template_text(stage)
        for token in FORBIDDEN_TOKENS_BY_STAGE[stage]:
            assert token not in template_text, f"{stage} 模板出现越权内容：{token}"


class TestStageResponsibilities:
    """三份 Prompt 各自只描述本阶段职责，包含对应受控词表与硬规则。"""

    @pytest.mark.parametrize("stage", STAGES)
    def test_required_responsibility_content(self, stage: str) -> None:
        template_text = _template_text(stage)
        for token in REQUIRED_CONTENT_BY_STAGE[stage]:
            assert token in template_text, f"{stage} 模板缺少职责内容：{token}"


class TestV1TemplateSnapshot:
    """Prompt 快照：v1 模板内容与冻结指纹一致，防止无意修改。"""

    @pytest.mark.parametrize("stage", STAGES)
    def test_template_matches_v1_snapshot(self, stage: str) -> None:
        template_text = _template_text(stage)
        digest = hashlib.sha256(template_text.encode("utf-8")).hexdigest()
        assert digest == V1_TEMPLATE_SHA256[stage], (
            f"{stage} 模板内容偏离 v1 快照：如为有意修订，请提升版本并更新快照"
        )
