"""M1-04：批次导入仓储（技术实施规格 5.4/8/11.1/11.2；ADR-0036/0079）。

把通过校验的包在单个同步短事务内原子写入 data_versions/batches/cases/evidence
四表（规格 11.2：每个请求使用独立同步 Session，事务内不等待外部 IO）：

- data_version 全局唯一：同一 data_version 已存在时复用已有行，不重复落库；
  demo_batch_v1 与 acceptance_batch_v1 共享 mock_dataset_v1 即此场景；
- batch_id 全局唯一、case_id 批次内唯一、evidence_id 案例内唯一，违反约束时
  IntegrityError 向上抛给 BatchImportGateway，由网关回滚正式目录并转幂等/冲突；
- 图片只存相对运行目录的路径、媒体类型与哈希，不存 BLOB（规格 11.2）；
- 源数据没有发生时间时不补造 occurred_at（规格 5.6/11.2）。

evidence 表的 payload_json 保存该条证据的类型专属内容（文本正文、图片路径、
行为事实与数值），sequence_no 对文本用合同序号，对图片/行为用组内固定 0 基下标
（合同只给文本 sequence_no，正式投影需稳定序号）。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.contracts.data import BatchManifest, CaseInput
from app.contracts.states import BatchStatus, CaseStatus
from app.modules.data.db.models import (
    Batch,
    Case,
    DataVersion,
    Evidence,
)

# evidence.payload_json 省略的公共字段（已进入独立列，不在 payload 重复）。
_EVIDENCE_PAYLOAD_EXCLUDE: set[str] = {
    "evidence_id",
    "identity",
    "relation_identity",
    "source_ref",
    "content_hash",
}


def _evidence_row(
    case_row_id: int,
    *,
    evidence_id: str,
    modality: str,
    sequence_no: int,
    identity: str,
    relation_identity: str,
    source_ref_json: dict[str, Any],
    content_hash: str,
    relative_path: str,
    media_type: str,
    payload_json: dict[str, Any],
) -> Evidence:
    """构造一条 evidence 行；源数据没有发生时间，occurred_at 保持 None。"""
    return Evidence(
        case_id=case_row_id,
        evidence_id=evidence_id,
        modality=modality,
        sequence_no=sequence_no,
        identity=identity,
        relation_identity=relation_identity,
        source_ref_json=source_ref_json,
        content_hash=content_hash,
        occurred_at=None,
        relative_path=relative_path,
        media_type=media_type,
        payload_json=payload_json,
    )


def _build_evidence_rows(case: CaseInput, case_row_id: int) -> list[Evidence]:
    """把 CaseInput 三类证据映射为 evidence 行（图片不存 BLOB，路径与哈希入库）。"""
    rows: list[Evidence] = []
    for item in case.evidence.text_items:
        rows.append(
            _evidence_row(
                case_row_id,
                evidence_id=item.evidence_id,
                modality="text",
                sequence_no=item.sequence_no,
                identity=item.identity.value,
                relation_identity=item.relation_identity.value,
                source_ref_json=item.source_ref.model_dump(mode="json"),
                content_hash=item.content_hash,
                relative_path="",
                media_type="text/plain",
                payload_json=item.model_dump(
                    exclude=_EVIDENCE_PAYLOAD_EXCLUDE, exclude_none=True, mode="json"
                ),
            )
        )
    for index, item in enumerate(case.evidence.image_items):
        rows.append(
            _evidence_row(
                case_row_id,
                evidence_id=item.evidence_id,
                modality="image",
                sequence_no=index,
                identity=item.identity.value,
                relation_identity=item.relation_identity.value,
                source_ref_json=item.source_ref.model_dump(mode="json"),
                content_hash=item.content_hash,
                relative_path=item.asset_relative_path,
                media_type=item.media_type.value,
                payload_json=item.model_dump(
                    exclude=_EVIDENCE_PAYLOAD_EXCLUDE, exclude_none=True, mode="json"
                ),
            )
        )
    for index, item in enumerate(case.evidence.behavior_items):
        rows.append(
            _evidence_row(
                case_row_id,
                evidence_id=item.evidence_id,
                modality="behavior",
                sequence_no=index,
                identity=item.identity.value,
                relation_identity=item.relation_identity.value,
                source_ref_json=item.source_ref.model_dump(mode="json"),
                content_hash=item.content_hash,
                relative_path="",
                media_type="",
                payload_json=item.model_dump(
                    exclude=_EVIDENCE_PAYLOAD_EXCLUDE, exclude_none=True, mode="json"
                ),
            )
        )
    return rows


class BatchImportRepository:
    """九表查询与原子写入（data_versions/batches/cases/evidence）的轻量仓储。"""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def find_batch_by_package_sha256(self, package_sha256: str) -> Batch | None:
        """按包哈希查已有批次（幂等识别；规格 5.4：同包返回原批次）。"""
        with Session(self._engine) as session:
            return session.scalar(
                select(Batch).where(Batch.package_sha256 == package_sha256)
            )

    def find_batch_by_batch_id(self, batch_id: str) -> Batch | None:
        """按全局唯一 batch_id 查已有批次（规格 5.4：批次冲突识别）。"""
        with Session(self._engine) as session:
            return session.scalar(select(Batch).where(Batch.batch_id == batch_id))

    def evidence_count_for_batch(self, batch_internal_id: int) -> int:
        """给定批次内部 ID 的 evidence 行数（规格 12.2：evidence_count 由表计数）。"""
        with Session(self._engine) as session:
            count = session.scalar(
                select(func.count(Evidence.id))
                .join(Case, Evidence.case_id == Case.id)
                .where(Case.batch_id == batch_internal_id)
            )
            return int(count or 0)

    def persist_import(
        self,
        *,
        manifest: BatchManifest,
        cases: list[tuple[str, CaseInput]],
        package_sha256: str,
        package_relative_path: str,
    ) -> str:
        """在单个短事务内写入四表；约束冲突抛 IntegrityError，由网关回滚清理。

        返回全局唯一 batch_id。data_version 已存在时复用其行（不重复落库）；
        所有时间统一取同一 UTC 毫秒时间戳（规格 11.2）。
        """
        now = datetime.now(UTC)
        session = Session(self._engine)
        try:
            data_version_row = session.scalar(
                select(DataVersion).where(DataVersion.data_version == manifest.data_version)
            )
            if data_version_row is None:
                provenance = cases[0][1].provenance
                data_version_row = DataVersion(
                    data_version=manifest.data_version,
                    source_snapshot_ref=manifest.source_snapshot_at.isoformat(),
                    source_manifest_sha256=provenance.source_manifest_sha256,
                    provenance_json=provenance.model_dump(mode="json"),
                    created_at=now,
                )
                session.add(data_version_row)
                session.flush()

            batch_row = Batch(
                batch_id=manifest.batch_id,
                data_version_id=data_version_row.id,
                schema_version=manifest.schema_version,
                package_sha256=package_sha256,
                package_relative_path=package_relative_path,
                status=BatchStatus.PENDING_ANALYSIS,
                case_count=manifest.case_count,
                analysis_succeeded_count=0,
                error_count=0,
                imported_at=now,
                updated_at=now,
            )
            session.add(batch_row)
            session.flush()

            for _case_file, case in cases:
                case_row = Case(
                    batch_id=batch_row.id,
                    case_id=case.case_id,
                    schema_version=case.schema_version,
                    case_input_json=case.model_dump(mode="json"),
                    customer_display_id=case.customer.customer_ref,
                    is_high_value=case.customer_value.is_high_value,
                    status=CaseStatus.PENDING_ANALYSIS,
                    imported_at=now,
                    updated_at=now,
                )
                session.add(case_row)
                session.flush()
                for evidence_row in _build_evidence_rows(case, case_row.id):
                    session.add(evidence_row)

            session.commit()
            return manifest.batch_id
        except IntegrityError:
            session.rollback()
            raise
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
