import pytest

from app.services.rag import rag_service


def test_chunk_text_short_text_single_chunk():
    assert rag_service.chunk_text("短文本") == ["短文本"]


def test_chunk_text_empty_returns_empty_list():
    assert rag_service.chunk_text("") == []
    assert rag_service.chunk_text(None) == []


def test_chunk_text_long_text_overlaps():
    text = "字" * 1000
    chunks = rag_service.chunk_text(text, chunk_size=512, overlap=128)
    assert len(chunks) > 1
    # 相邻分块之间应当有重叠
    assert chunks[0][-128:] == chunks[1][:128]


def test_hash_embedding_is_deterministic():
    v1 = rag_service._hash_embedding("轴承振动异常", 64)
    v2 = rag_service._hash_embedding("轴承振动异常", 64)
    assert v1 == v2
    assert len(v1) == 64


def test_hash_embedding_similar_text_more_similar_than_unrelated():
    import math

    def cosine(a, b):
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a)) or 1.0
        nb = math.sqrt(sum(x * x for x in b)) or 1.0
        return dot / (na * nb)

    base = rag_service._hash_embedding("轴承振动异常 高温预警", 128)
    similar = rag_service._hash_embedding("轴承振动异常 高温", 128)
    unrelated = rag_service._hash_embedding("财务报销流程说明", 128)

    assert cosine(base, similar) > cosine(base, unrelated)


@pytest.mark.asyncio
async def test_generate_answer_with_no_contexts_is_honest_about_no_evidence():
    answer, used_real = await rag_service.generate_answer("任意问题", [])
    assert "暂无充分依据" in answer


def test_confidence_hint_empty_results_is_low():
    from app.services.rag.router import _confidence_hint
    assert _confidence_hint([]) == "low"


def test_confidence_hint_high_when_strong_top_score_and_enough_hits():
    from app.services.rag.router import _confidence_hint
    results = [{"score": 0.9}, {"score": 0.85}, {"score": 0.8}]
    assert _confidence_hint(results) == "high"


def test_confidence_hint_medium_when_moderate_score():
    from app.services.rag.router import _confidence_hint
    results = [{"score": 0.6}]
    assert _confidence_hint(results) == "medium"


def test_confidence_hint_low_when_weak_score():
    from app.services.rag.router import _confidence_hint
    results = [{"score": 0.2}]
    assert _confidence_hint(results) == "low"
