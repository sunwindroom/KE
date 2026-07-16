"""知识冲突检测服务。

真实的语义冲突检测（例如"同一故障模式的两条处置建议互相矛盾"）需要语义理解能力，
超出规则/降级方案能做到的范围。这里采用一个诚实、可解释的启发式：同一领域内标题
高度相似的知识条目很可能是重复录入或存在分歧的表述，值得转交专家仲裁——这是可以
不依赖大模型稳定给出的信号，不是编造的示例数据。
"""
from __future__ import annotations

import difflib
from uuid import uuid4

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import KnowledgeConflict, KnowledgeItem

SIMILARITY_THRESHOLD = 0.72
ACTIVE_STATUSES = ("draft", "pending", "published")


async def detect_conflicts_for(db: AsyncSession, item: KnowledgeItem) -> list[KnowledgeConflict]:
    stmt = select(KnowledgeItem).where(
        KnowledgeItem.domain == item.domain,
        KnowledgeItem.id != item.id,
        KnowledgeItem.status.in_(ACTIVE_STATUSES),
    )
    result = await db.execute(stmt)
    created: list[KnowledgeConflict] = []

    for other in result.scalars().all():
        ratio = difflib.SequenceMatcher(None, item.title or "", other.title or "").ratio()
        if ratio < SIMILARITY_THRESHOLD:
            continue

        exists_stmt = select(KnowledgeConflict).where(
            KnowledgeConflict.status == "pending",
            or_(
                and_(KnowledgeConflict.knowledge_id_a == item.id, KnowledgeConflict.knowledge_id_b == other.id),
                and_(KnowledgeConflict.knowledge_id_a == other.id, KnowledgeConflict.knowledge_id_b == item.id),
            ),
        )
        exists_result = await db.execute(exists_stmt)
        if exists_result.scalar_one_or_none() is not None:
            continue

        conflict = KnowledgeConflict(
            id=f"CF{uuid4().hex[:10]}",
            knowledge_id_a=item.id,
            knowledge_id_b=other.id,
            domain=item.domain,
            conflict_type="similar_title",
            description=f"标题高度相似（相似度 {ratio:.2f}）：《{item.title}》 与 《{other.title}》，可能是重复录入或存在分歧表述。",
            similarity=round(ratio, 3),
            status="pending",
        )
        db.add(conflict)
        created.append(conflict)

    return created
