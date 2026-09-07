"""M1-06：EvidenceGateway 只读仓储（规格 11.1 证据读取路径）。

按公开标识定位 批次→案例→证据 三级记录，只返回 ORM 行、不做业务判断；
模态/媒体类型、路径越界与内容哈希校验在网关层。每次查询使用独立 Session，
不跨调用持有连接。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from ..db.models import Batch, Case, Evidence


class EvidenceRepository:
    """证据流只读仓储：批次/案例/证据的三级定位。"""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def batch_by_batch_id(self, batch_id: str) -> Batch | None:
        """按公开 batch_id 定位批次；不存在返回 None（规格 11.1 唯一）。"""
        with Session(self._engine) as session:
            return session.scalar(select(Batch).where(Batch.batch_id == batch_id))

    def case_of_batch(self, batch_internal_id: int, case_id: str) -> Case | None:
        """批次内唯一 (batch_id, case_id) 的案例（规格 11.1）。"""
        with Session(self._engine) as session:
            return session.scalar(
                select(Case).where(
                    Case.batch_id == batch_internal_id, Case.case_id == case_id
                )
            )

    def evidence_of_case(
        self, case_internal_id: int, evidence_id: str
    ) -> Evidence | None:
        """案例内唯一 (case_id, evidence_id) 的证据行（规格 11.1）。"""
        with Session(self._engine) as session:
            return session.scalar(
                select(Evidence).where(
                    Evidence.case_id == case_internal_id,
                    Evidence.evidence_id == evidence_id,
                )
            )


__all__ = ["EvidenceRepository"]
