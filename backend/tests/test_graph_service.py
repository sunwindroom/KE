import pytest

from app.services.ontology import graph_service


class FakeNode(dict):
    """最小化模拟 neo4j.graph.Node：既是属性映射，也带 .labels。"""

    def __init__(self, labels, **props):
        super().__init__(**props)
        self.labels = labels


def test_node_to_dict_extracts_specific_label_as_type():
    node = FakeNode(["Entity", "FailureMode"], id="FM001", name="轴承磨损", domain="energy", severity="high")
    result = graph_service._node_to_dict(node)
    assert result["id"] == "FM001"
    assert result["name"] == "轴承磨损"
    assert result["type"] == "FailureMode"
    assert result["domain"] == "energy"
    assert result["properties"] == {"severity": "high"}


def test_node_to_dict_falls_back_to_stored_type_property():
    node = FakeNode(["Entity", "Knowledge"], id="KI001", name="标题", type="Knowledge", knowledgeType="case")
    result = graph_service._node_to_dict(node)
    assert result["type"] == "Knowledge"
    assert result["properties"] == {"knowledgeType": "case"}


def test_node_to_dict_defaults_name_to_id_when_missing():
    node = FakeNode(["Entity", "Component"], id="C001")
    result = graph_service._node_to_dict(node)
    assert result["name"] == "C001"


@pytest.mark.asyncio
async def test_upsert_entity_rejects_unknown_type():
    with pytest.raises(ValueError):
        await graph_service.upsert_entity(session=None, entity_id="X1", name="test", entity_type="NotARealType", domain=None)


@pytest.mark.asyncio
async def test_create_relation_rejects_unknown_relation_type():
    with pytest.raises(ValueError):
        await graph_service.create_relation(session=None, source_id="A", target_id="B", relation="NOT_A_REAL_RELATION")


def test_valid_node_labels_cover_ontology_classes():
    from app.services.ontology.router import DEFAULT_CLASSES
    class_names = {c["className"] for c in DEFAULT_CLASSES}
    assert class_names.issubset(graph_service.VALID_NODE_LABELS)


def test_valid_relation_types_cover_ontology_relations():
    from app.services.ontology.router import DEFAULT_RELATIONS
    relation_names = {r["name"] for r in DEFAULT_RELATIONS}
    assert relation_names.issubset(graph_service.VALID_RELATION_TYPES)
