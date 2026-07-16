import asyncio
from unittest.mock import AsyncMock, MagicMock

from app.core.auth import SecurityContext
from app.services.rag import rag_service


def _ctx(max_level="internal", domain_scope=("energy",)):
    return SecurityContext(
        user_id="u1", user_name="test", role="engineer",
        domain_scope=list(domain_scope), max_classification_level=max_level,
    )


def _fake_db(rows):
    fake_result = MagicMock()
    fake_result.all.return_value = rows
    fake_db = AsyncMock()
    fake_db.execute = AsyncMock(return_value=fake_result)
    return fake_db


def test_filter_by_access_denies_over_clearance_results():
    ctx = _ctx(max_level="internal")
    db = _fake_db([("K1", "secret", "energy"), ("K2", "internal", "energy")])
    results = [
        {"knowledgeId": "K1", "title": "机密条目", "score": 0.9},
        {"knowledgeId": "K2", "title": "普通条目", "score": 0.8},
    ]
    filtered = asyncio.run(rag_service.filter_by_access(db, results, ctx))
    assert [r["knowledgeId"] for r in filtered] == ["K2"]


def test_filter_by_access_denies_out_of_scope_domain():
    ctx = _ctx(max_level="secret", domain_scope=("energy",))
    db = _fake_db([("K1", "internal", "aerospace")])
    results = [{"knowledgeId": "K1", "title": "航空条目", "score": 0.9}]
    filtered = asyncio.run(rag_service.filter_by_access(db, results, ctx))
    assert filtered == []


def test_filter_by_access_denies_results_with_no_matching_metadata():
    ctx = _ctx(max_level="secret")
    db = _fake_db([])  # 数据库里查不到对应的知识条目元数据
    results = [{"knowledgeId": "GHOST", "title": "幽灵结果", "score": 0.9}]
    filtered = asyncio.run(rag_service.filter_by_access(db, results, ctx))
    assert filtered == []


def test_filter_by_access_empty_results_short_circuits():
    ctx = _ctx()
    db = _fake_db([])
    filtered = asyncio.run(rag_service.filter_by_access(db, [], ctx))
    assert filtered == []
