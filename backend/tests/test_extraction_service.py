from app.services.extraction import extraction_service as es


def test_extract_with_rules_finds_leads_to_relation():
    text = "轴承磨损导致异常振动。冷却器属于液压系统。"
    result = es.extract_with_rules(text, "energy")
    relation_types = {r["relation"] for r in result["relations"]}
    assert "LEADS_TO" in relation_types
    assert "BELONGS_TO" in relation_types


def test_extract_with_rules_no_match_returns_empty():
    result = es.extract_with_rules("这是一段完全不相关的说明文字。", "general")
    assert result["entities"] == []
    assert result["relations"] == []


def test_extract_with_rules_skips_self_relations():
    text = "润滑油导致润滑油。"
    result = es.extract_with_rules(text, "energy")
    assert result["relations"] == []


def test_guess_entity_type_uses_keyword_hints():
    assert es._guess_entity_type("轴承磨损故障") == "FailureMode"
    assert es._guess_entity_type("异常振动征兆") == "Symptom"
    assert es._guess_entity_type("未知设备XYZ") == "Equipment"


def test_parse_llm_json_strips_markdown_fences():
    raw = '```json\n{"entities": [], "relations": []}\n```'
    parsed = es._parse_llm_json(raw)
    assert parsed == {"entities": [], "relations": []}


def test_parse_llm_json_extracts_embedded_object():
    raw = '这是一些解释性文字\n{"entities": [{"id": "a", "name": "轴承"}], "relations": []}\n谢谢'
    parsed = es._parse_llm_json(raw)
    assert parsed is not None
    assert parsed["entities"][0]["name"] == "轴承"


def test_parse_llm_json_returns_none_for_garbage():
    assert es._parse_llm_json("not json at all") is None


def test_clamp_confidence_bounds_values():
    assert es._clamp_confidence(1.5) == 1.0
    assert es._clamp_confidence(-0.5) == 0.0
    assert es._clamp_confidence(0.42) == 0.42
    assert es._clamp_confidence("garbage", default=0.7) == 0.7


def test_summarize_extraction_lists_entities_and_relations():
    result = {
        "entities": [{"name": "轴承", "type": "Component"}],
        "relations": [{"source_name": "轴承", "relation": "LEADS_TO", "target_name": "振动"}],
    }
    summary = es.summarize_extraction(result)
    assert "轴承" in summary
    assert "LEADS_TO" in summary


def test_summarize_extraction_empty_result_is_honest():
    summary = es.summarize_extraction({"entities": [], "relations": []})
    assert "未抽取到" in summary
