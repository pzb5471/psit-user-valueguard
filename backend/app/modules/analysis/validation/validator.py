"""阶段结果严格校验器（M2-04，规格第 5.6、7.4、9.2、9.4 节）。

集中完成规格第 9.4 节七步校验：JSON 解析、Pydantic 严格校验、case_id、
证据归属与阶段允许集合、跨阶段引用、密封答案禁止内容、动作目录与最低介入规则。
允许证据集合由调用方传入（从 CaseInput 派生属于 M3 装配职责），校验器
不导入 M1 数据合同代码；错误全部结构化，供 M2-08 做一次定向修复。
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from app.contracts.analysis import (
    ActionType,
    AnalysisStage,
    AttributionResult,
    DecisionPackage,
    InterventionLevel,
    PerceptionResult,
)
from app.modules.analysis.validation.errors import (
    StageValidationError,
    ValidationErrorCode,
)

__all__ = [
    "AttributionValidationContext",
    "PerceptionValidationContext",
    "StageValidationOutcome",
    "StrategyValidationContext",
    "perception_cited_evidence_ids",
    "validate_stage_result",
]

_SEALED_ANSWER_TOKENS = (
    "key_answer",
    "database_gt",
    "user_profile",
    "user_profile_st1",
    "question_type",
    "trajectory",
)

_MAX_REPORTED_SCHEMA_ERRORS = 10

@dataclass(frozen=True)
class PerceptionValidationContext:
    """感知阶段校验上下文：当前案例、允许编号与字段级证据类型集合。"""

    case_id: str
    allowed_evidence_ids: frozenset[str]
    customer_text_evidence_ids: frozenset[str]
    text_evidence_ids: frozenset[str]
    image_evidence_ids: frozenset[str]


@dataclass(frozen=True)
class AttributionValidationContext:
    """归因阶段校验上下文：案例允许集合 + 感知阶段实际引用的证据编号。"""

    case_id: str
    allowed_evidence_ids: frozenset[str]
    upstream_cited_ids: frozenset[str]


@dataclass(frozen=True)
class StrategyValidationContext:
    """策略阶段校验上下文：允许集合、获准引用、动作目录与最低介入底线输入。"""

    case_id: str
    allowed_evidence_ids: frozenset[str]
    upstream_cited_ids: frozenset[str]
    catalog_action_types: frozenset[str]
    severe_unresolved_present: bool
    evidence_conflict_or_insufficient: bool


@dataclass(frozen=True)
class StageValidationOutcome:
    """校验结果：全部通过时携带解析后的严格结果，否则携带结构化错误。"""

    stage: AnalysisStage
    result: PerceptionResult | AttributionResult | DecisionPackage | None
    errors: tuple[StageValidationError, ...]

    @property
    def ok(self) -> bool:
        return not self.errors


def perception_cited_evidence_ids(perception: PerceptionResult) -> frozenset[str]:
    """感知阶段实际引用的全部证据编号（归因阶段允许集合的派生规则）。"""

    return frozenset(evidence_id for _, evidence_id in _perception_evidence_refs(perception))


def validate_stage_result(
    stage: AnalysisStage, raw_json: str, context: Any
) -> StageValidationOutcome:
    """按规格第 9.4 节顺序校验一个阶段结果；阶段与上下文必须一一匹配。"""

    match stage:
        case AnalysisStage.PERCEPTION:
            if not isinstance(context, PerceptionValidationContext):
                raise ValueError("感知阶段需要 PerceptionValidationContext")
            return _validate_perception(raw_json, context)
        case AnalysisStage.ATTRIBUTION:
            if not isinstance(context, AttributionValidationContext):
                raise ValueError("归因阶段需要 AttributionValidationContext")
            return _validate_attribution(raw_json, context)
        case AnalysisStage.STRATEGY:
            if not isinstance(context, StrategyValidationContext):
                raise ValueError("策略阶段需要 StrategyValidationContext")
            return _validate_strategy(raw_json, context)
        case _:
            raise ValueError(f"未知分析阶段：{stage!r}")


def _validate_perception(
    raw_json: str, context: PerceptionValidationContext
) -> StageValidationOutcome:
    result, parse_errors = _parse(PerceptionResult, AnalysisStage.PERCEPTION, raw_json)
    if parse_errors or result is None:
        return StageValidationOutcome(AnalysisStage.PERCEPTION, None, parse_errors)

    errors: list[StageValidationError] = []
    errors += _check_case_id(result, context.case_id)
    errors += _check_evidence(
        AnalysisStage.PERCEPTION,
        _perception_evidence_refs(result),
        context.allowed_evidence_ids,
        upstream_cited_ids=None,
    )
    errors += _check_perception_evidence_types(result, context)
    errors += _scan_forbidden_content(AnalysisStage.PERCEPTION, result)
    return StageValidationOutcome(
        AnalysisStage.PERCEPTION, result if not errors else None, tuple(errors)
    )


def _validate_attribution(
    raw_json: str, context: AttributionValidationContext
) -> StageValidationOutcome:
    result, parse_errors = _parse(AttributionResult, AnalysisStage.ATTRIBUTION, raw_json)
    if parse_errors or result is None:
        return StageValidationOutcome(AnalysisStage.ATTRIBUTION, None, parse_errors)

    errors: list[StageValidationError] = []
    errors += _check_case_id(result, context.case_id)
    errors += _check_evidence(
        AnalysisStage.ATTRIBUTION,
        _attribution_evidence_refs(result),
        context.allowed_evidence_ids,
        upstream_cited_ids=context.upstream_cited_ids,
    )
    errors += _scan_forbidden_content(AnalysisStage.ATTRIBUTION, result)
    return StageValidationOutcome(
        AnalysisStage.ATTRIBUTION, result if not errors else None, tuple(errors)
    )


def _validate_strategy(
    raw_json: str, context: StrategyValidationContext
) -> StageValidationOutcome:
    result, parse_errors = _parse(DecisionPackage, AnalysisStage.STRATEGY, raw_json)
    if parse_errors or result is None:
        return StageValidationOutcome(AnalysisStage.STRATEGY, None, parse_errors)

    errors: list[StageValidationError] = []
    errors += _check_case_id(result, context.case_id)
    errors += _check_evidence(
        AnalysisStage.STRATEGY,
        _strategy_evidence_refs(result),
        context.allowed_evidence_ids,
        upstream_cited_ids=context.upstream_cited_ids,
    )
    errors += _scan_forbidden_content(AnalysisStage.STRATEGY, result)
    errors += _check_action_catalog(result, context.catalog_action_types)
    errors += _check_minimum_intervention(result, context)
    return StageValidationOutcome(
        AnalysisStage.STRATEGY, result if not errors else None, tuple(errors)
    )


def _parse[StageResultT: (PerceptionResult, AttributionResult, DecisionPackage)](
    model: type[StageResultT],
    stage: AnalysisStage,
    raw_json: str,
) -> tuple[StageResultT | None, tuple[StageValidationError, ...]]:
    try:
        result = model.model_validate_json(raw_json)
    except ValidationError as error:
        errors: list[StageValidationError] = []
        for item in error.errors()[:_MAX_REPORTED_SCHEMA_ERRORS]:
            code = (
                ValidationErrorCode.JSON_PARSE_FAILED
                if str(item.get("type", "")).startswith("json")
                else ValidationErrorCode.SCHEMA_VALIDATION_FAILED
            )
            field_path = ".".join(str(part) for part in item.get("loc", ())) or "<root>"
            errors.append(
                StageValidationError(
                    code=code,
                    stage=stage,
                    field_path=field_path,
                    message=str(item.get("msg", "校验失败")),
                    repairable=True,
                )
            )
        return None, tuple(errors)
    return result, ()


def _check_case_id(
    result: PerceptionResult | AttributionResult | DecisionPackage, case_id: str
) -> list[StageValidationError]:
    if result.case_id == case_id:
        return []
    return [
        StageValidationError(
            code=ValidationErrorCode.CASE_ID_MISMATCH,
            stage=_stage_of(result),
            field_path="case_id",
            message=f"结果 case_id {result.case_id} 与当前案例 {case_id} 不一致",
            repairable=True,
        )
    ]


def _stage_of(
    result: PerceptionResult | AttributionResult | DecisionPackage,
) -> AnalysisStage:
    if isinstance(result, PerceptionResult):
        return AnalysisStage.PERCEPTION
    if isinstance(result, AttributionResult):
        return AnalysisStage.ATTRIBUTION
    return AnalysisStage.STRATEGY


def _perception_evidence_refs(
    result: PerceptionResult,
) -> Iterator[tuple[str, str]]:
    for index, event in enumerate(result.events):
        for evidence_id in event.evidence_ids:
            yield f"events[{index}].evidence_ids", evidence_id
        if event.conflict_evidence_ids is not None:
            for evidence_id in event.conflict_evidence_ids:
                yield f"events[{index}].conflict_evidence_ids", evidence_id
    for evidence_id in result.emotion.evidence_ids:
        yield "emotion.evidence_ids", evidence_id
    for index, observation in enumerate(result.image_observations):
        yield f"image_observations[{index}].image_evidence_id", observation.image_evidence_id
        if observation.related_text_evidence_ids is not None:
            for evidence_id in observation.related_text_evidence_ids:
                yield (
                    f"image_observations[{index}].related_text_evidence_ids",
                    evidence_id,
                )


def _attribution_evidence_refs(
    result: AttributionResult,
) -> Iterator[tuple[str, str]]:
    causes: list[tuple[str, Any]] = [("primary_cause", result.primary_cause)]
    if result.alternative_cause is not None:
        causes.append(("alternative_cause", result.alternative_cause))
    for field_name, cause in causes:
        for evidence_id in cause.evidence_ids:
            yield f"{field_name}.evidence_ids", evidence_id
        if cause.counter_evidence_ids is not None:
            for evidence_id in cause.counter_evidence_ids:
                yield f"{field_name}.counter_evidence_ids", evidence_id


def _strategy_evidence_refs(
    result: DecisionPackage,
) -> Iterator[tuple[str, str]]:
    for index, action in enumerate(result.actions):
        for evidence_id in action.evidence_ids:
            yield f"actions[{index}].evidence_ids", evidence_id


def _check_evidence(
    stage: AnalysisStage,
    refs: Iterator[tuple[str, str]],
    allowed_evidence_ids: frozenset[str],
    upstream_cited_ids: frozenset[str] | None,
) -> list[StageValidationError]:
    errors: list[StageValidationError] = []
    for field_path, evidence_id in refs:
        if evidence_id not in allowed_evidence_ids:
            errors.append(
                StageValidationError(
                    code=ValidationErrorCode.EVIDENCE_NOT_ALLOWED,
                    stage=stage,
                    field_path=field_path,
                    message=f"证据 {evidence_id} 不属于当前案例允许集合",
                    repairable=True,
                )
            )
        elif upstream_cited_ids is not None and evidence_id not in upstream_cited_ids:
            errors.append(
                StageValidationError(
                    code=ValidationErrorCode.CROSS_STAGE_REFERENCE_INVALID,
                    stage=stage,
                    field_path=field_path,
                    message=f"证据 {evidence_id} 未被上游阶段引用，越权引用",
                    repairable=True,
                )
            )
    return errors


def _check_perception_evidence_types(
    result: PerceptionResult, context: PerceptionValidationContext
) -> list[StageValidationError]:
    """情绪只引客户文本，图片观察与关联文本不得串用证据模态。"""

    errors: list[StageValidationError] = []

    def check(
        field_path: str,
        evidence_ids: Iterator[str],
        expected_ids: frozenset[str],
        expected_label: str,
    ) -> None:
        for evidence_id in evidence_ids:
            if (
                evidence_id not in context.allowed_evidence_ids
                or evidence_id in expected_ids
            ):
                continue
            errors.append(
                StageValidationError(
                    code=ValidationErrorCode.EVIDENCE_NOT_ALLOWED,
                    stage=AnalysisStage.PERCEPTION,
                    field_path=field_path,
                    message=f"证据 {evidence_id} 不是{expected_label}，不得用于该字段",
                    repairable=True,
                )
            )

    check(
        "emotion.evidence_ids",
        iter(result.emotion.evidence_ids),
        context.customer_text_evidence_ids,
        "客户文本证据",
    )
    for index, observation in enumerate(result.image_observations):
        check(
            f"image_observations[{index}].image_evidence_id",
            iter((observation.image_evidence_id,)),
            context.image_evidence_ids,
            "图片证据",
        )
        check(
            f"image_observations[{index}].related_text_evidence_ids",
            iter(observation.related_text_evidence_ids or ()),
            context.text_evidence_ids,
            "文本证据",
        )
    return errors


def _scan_forbidden_content(
    stage: AnalysisStage, result: PerceptionResult | AttributionResult | DecisionPackage
) -> list[StageValidationError]:
    errors: list[StageValidationError] = []

    def walk(value: Any, path: str) -> None:
        if isinstance(value, str):
            lowered = value.lower()
            for token in _SEALED_ANSWER_TOKENS:
                if token in lowered:
                    errors.append(
                        StageValidationError(
                            code=ValidationErrorCode.FORBIDDEN_CONTENT,
                            stage=stage,
                            field_path=path,
                            message=f"结果包含密封答案字段名 {token}，属于不可重试污染",
                            repairable=False,
                        )
                    )
                    return
            return
        if isinstance(value, dict):
            for key, item in value.items():
                walk(item, f"{path}.{key}" if path else str(key))
            return
        if isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{path}[{index}]")

    walk(result.model_dump(mode="python"), "")
    return errors


def _check_action_catalog(
    result: DecisionPackage, catalog_action_types: frozenset[str]
) -> list[StageValidationError]:
    errors: list[StageValidationError] = []
    for index, action in enumerate(result.actions):
        if action.action_type.value not in catalog_action_types:
            errors.append(
                StageValidationError(
                    code=ValidationErrorCode.ACTION_CATALOG_VIOLATION,
                    stage=AnalysisStage.STRATEGY,
                    field_path=f"actions[{index}].action_type",
                    message=f"动作 {action.action_type.value} 不在动作目录内",
                    repairable=True,
                )
            )
    return errors


def _check_minimum_intervention(
    result: DecisionPackage, context: StrategyValidationContext
) -> list[StageValidationError]:
    if (
        result.intervention_level is not InterventionLevel.NO_IMMEDIATE_INTERVENTION
        and all(
            action.action_type is ActionType.NO_ACTION_MONITOR
            for action in result.actions
        )
    ):
        return [
            StageValidationError(
                code=ValidationErrorCode.MINIMUM_INTERVENTION_VIOLATION,
                stage=AnalysisStage.STRATEGY,
                field_path="actions",
                message="建议或必须介入时，动作不能只有 NO_ACTION_MONITOR",
                repairable=True,
            )
        ]
    if result.intervention_level is not InterventionLevel.NO_IMMEDIATE_INTERVENTION:
        return []
    errors: list[StageValidationError] = []
    if context.severe_unresolved_present:
        errors.append(
            StageValidationError(
                code=ValidationErrorCode.MINIMUM_INTERVENTION_VIOLATION,
                stage=AnalysisStage.STRATEGY,
                field_path="intervention_level",
                message="存在未解决的严重问题，不得给 NO_IMMEDIATE_INTERVENTION",
                repairable=True,
            )
        )
    if context.evidence_conflict_or_insufficient:
        errors.append(
            StageValidationError(
                code=ValidationErrorCode.MINIMUM_INTERVENTION_VIOLATION,
                stage=AnalysisStage.STRATEGY,
                field_path="intervention_level",
                message="严重问题存在证据冲突或不足时至少为 SHOULD_INTERVENE，并明确需要人工核验",
                repairable=True,
            )
        )
    if any(
        action.action_type is not ActionType.NO_ACTION_MONITOR
        for action in result.actions
    ):
        errors.append(
            StageValidationError(
                code=ValidationErrorCode.MINIMUM_INTERVENTION_VIOLATION,
                stage=AnalysisStage.STRATEGY,
                field_path="actions",
                message="NO_IMMEDIATE_INTERVENTION 只能搭配 NO_ACTION_MONITOR",
                repairable=True,
            )
        )
    return errors
