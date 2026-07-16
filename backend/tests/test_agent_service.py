from app.services.agent import agent_service


def test_format_context_with_graph_and_rag():
    graph_entity = {
        "name": "轴承",
        "type": "Component",
        "relations": [{"relation": "OCCURS_IN", "target": "FM001", "targetType": "FailureMode"}],
    }
    rag_results = [{"title": "轴承维护手册", "snippet": "定期检查振动值"}]
    text = agent_service._format_context_for_llm(rag_results, graph_entity)
    assert "轴承" in text
    assert "OCCURS_IN" in text
    assert "轴承维护手册" in text


def test_format_context_with_nothing_is_honest_about_no_evidence():
    text = agent_service._format_context_for_llm([], None)
    assert "未检索到" in text


def test_agent_runners_cover_all_frontend_agent_types():
    frontend_types = {"fault_diagnosis", "maintenance_strategy", "rul_prediction", "knowledge_review"}
    assert frontend_types.issubset(set(agent_service.AGENT_RUNNERS.keys()))


def test_knowledge_review_runner_does_not_require_confirmation():
    import asyncio
    from unittest.mock import AsyncMock, MagicMock

    fake_result = MagicMock()
    fake_result.scalars.return_value.all.return_value = []
    fake_db = AsyncMock()
    fake_db.execute = AsyncMock(return_value=fake_result)

    trace, conclusion, needs_confirmation = asyncio.run(
        agent_service.run_knowledge_review(fake_db, "任意查询", None)
    )
    assert needs_confirmation is False
    assert "未发现知识质量问题" in conclusion
    assert len(trace) == 3
