"""知识图谱数据访问层：所有与 Neo4j 的真实 Cypher 交互都集中在这里。

图数据建模约定：
- 每个实体节点都带有通用标签 `:Entity`，再叠加一个具体类型标签
  (例如 `:Entity:FailureMode`)，这样既可以写通用 Cypher（按 :Entity 检索），
  也能按具体类型做索引/约束。
- 节点通用属性：id（全局唯一）、name、domain、type（=具体类型标签，冗余存一份
  方便前端直接读取，不必再查标签）。
- 关系类型对应本体中定义的 BELONGS_TO / OCCURS_IN / MANIFESTS_AS / LEADS_TO /
  RESOLVED_BY / DETECTED_BY / APPLIES_MODEL，以及知识入图使用的 DOCUMENTED_BY。
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from neo4j import AsyncSession

logger = logging.getLogger(__name__)

# 与 ontology/router.py 中 DEFAULT_CLASSES 保持一致的合法节点类型集合，
# 用于防止把未知/非法标签拼进 Cypher 字符串（Neo4j 的标签名不能参数化）。
VALID_NODE_LABELS = {
    "Equipment", "Component", "FailureMode", "Symptom", "DiagnosisMethod",
    "HealthState", "RULModel", "MaintenanceStrategy", "Knowledge",
}

VALID_RELATION_TYPES = {
    "BELONGS_TO", "OCCURS_IN", "MANIFESTS_AS", "LEADS_TO", "RESOLVED_BY",
    "DETECTED_BY", "APPLIES_MODEL", "DOCUMENTED_BY",
}


async def ensure_constraints(session: AsyncSession) -> None:
    """在启动时确保唯一性约束存在（幂等，可重复调用）。"""
    await session.run(
        "CREATE CONSTRAINT entity_id_unique IF NOT EXISTS "
        "FOR (n:Entity) REQUIRE n.id IS UNIQUE"
    )


def _node_to_dict(node) -> dict[str, Any]:
    props = dict(node)
    specific_labels = [l for l in node.labels if l != "Entity"]
    return {
        "id": props.get("id"),
        "name": props.get("name", props.get("id")),
        "type": props.get("type") or (specific_labels[0] if specific_labels else "Entity"),
        "domain": props.get("domain"),
        "properties": {k: v for k, v in props.items() if k not in ("id", "name", "type", "domain")},
    }


async def resolve_entity_id(session: AsyncSession, query: str, domain: Optional[str] = None) -> Optional[str]:
    """把用户输入（可能是精确 id，也可能是模糊名称）解析成一个具体的实体 id。"""
    if not query:
        return None
    result = await session.run(
        """
        MATCH (n:Entity)
        WHERE n.id = $q OR toLower(n.name) CONTAINS toLower($q)
        AND ($domain IS NULL OR n.domain = $domain)
        RETURN n.id AS id
        ORDER BY CASE WHEN n.id = $q THEN 0 ELSE 1 END
        LIMIT 1
        """,
        q=query, domain=domain,
    )
    record = await result.single()
    return record["id"] if record else None


async def search_entities(session: AsyncSession, query: str, domain: Optional[str], limit: int = 20) -> list[dict]:
    result = await session.run(
        """
        MATCH (n:Entity)
        WHERE toLower(n.name) CONTAINS toLower($q)
        AND ($domain IS NULL OR n.domain = $domain)
        RETURN n
        LIMIT $limit
        """,
        q=query, domain=domain, limit=limit,
    )
    return [_node_to_dict(record["n"]) async for record in result]


async def get_entity_detail(session: AsyncSession, entity_id: str) -> Optional[dict]:
    result = await session.run(
        """
        MATCH (n:Entity {id: $id})
        OPTIONAL MATCH (n)-[r]->(out:Entity)
        WITH n, collect(DISTINCT {relation: type(r), target: out.id, targetType: out.type}) AS outRels
        OPTIONAL MATCH (n)<-[r2]-(in:Entity)
        WITH n, outRels, collect(DISTINCT {relation: type(r2), target: in.id, targetType: in.type}) AS inRels
        RETURN n, outRels + inRels AS relations
        """,
        id=entity_id,
    )
    record = await result.single()
    if record is None:
        return None
    node = _node_to_dict(record["n"])
    relations = [r for r in record["relations"] if r.get("relation") is not None]
    node["relations"] = relations
    return node


async def get_subgraph(
    session: AsyncSession,
    center_entity: Optional[str],
    depth: int,
    domain: Optional[str],
) -> dict:
    depth = max(1, min(depth, 5))

    if center_entity:
        center_id = await resolve_entity_id(session, center_entity, domain)
        if center_id is None:
            return {"nodes": [], "edges": []}
        result = await session.run(
            f"""
            MATCH (center:Entity {{id: $centerId}})
            OPTIONAL MATCH (center)-[*1..{depth}]-(other:Entity)
            WHERE $domain IS NULL OR other.domain = $domain OR other.domain IS NULL
            WITH center, collect(DISTINCT other) AS others
            RETURN center, others
            """,
            centerId=center_id, domain=domain,
        )
        record = await result.single()
        if record is None:
            return {"nodes": [], "edges": []}
        nodes = [_node_to_dict(record["center"])] + [_node_to_dict(n) for n in record["others"] if n is not None]
    else:
        # 未指定中心节点：按 domain 过滤返回一批节点（用于初次打开图谱空间时的整体概览）
        result = await session.run(
            """
            MATCH (n:Entity)
            WHERE $domain IS NULL OR n.domain = $domain
            RETURN n
            LIMIT 200
            """,
            domain=domain,
        )
        nodes = [_node_to_dict(record["n"]) async for record in result]

    if not nodes:
        return {"nodes": [], "edges": []}

    node_ids = [n["id"] for n in nodes]
    edge_result = await session.run(
        """
        MATCH (a:Entity)-[r]->(b:Entity)
        WHERE a.id IN $nodeIds AND b.id IN $nodeIds
        RETURN type(r) AS relType, a.id AS source, b.id AS target, properties(r) AS props
        """,
        nodeIds=node_ids,
    )
    edges = [
        {"source": rec["source"], "target": rec["target"], "relation": rec["relType"], "properties": dict(rec["props"] or {})}
        async for rec in edge_result
    ]
    return {"nodes": nodes, "edges": edges}


async def path_query(session: AsyncSession, from_entity: str, to_entity: str, max_hops: int) -> dict:
    max_hops = max(1, min(max_hops, 10))
    from_id = await resolve_entity_id(session, from_entity)
    to_id = await resolve_entity_id(session, to_entity)
    if from_id is None or to_id is None:
        return {"paths": []}

    result = await session.run(
        f"""
        MATCH (a:Entity {{id: $from}}), (b:Entity {{id: $to}})
        MATCH p = shortestPath((a)-[*..{max_hops}]-(b))
        RETURN [n IN nodes(p) | n.id] AS nodeIds,
               [n IN nodes(p) | n.name] AS nodeNames,
               [n IN nodes(p) | n.type] AS nodeTypes,
               [r IN relationships(p) | type(r)] AS relTypes
        """,
        **{"from": from_id, "to": to_id},
    )
    record = await result.single()
    if record is None:
        return {"paths": []}
    nodes = [
        {"id": nid, "name": name, "type": ntype}
        for nid, name, ntype in zip(record["nodeIds"], record["nodeNames"], record["nodeTypes"])
    ]
    return {"paths": [{"nodes": nodes, "relations": record["relTypes"]}]}


async def get_graph_stats(session: AsyncSession, domain: Optional[str]) -> dict:
    node_result = await session.run(
        """
        MATCH (n:Entity)
        WHERE $domain IS NULL OR n.domain = $domain
        RETURN labels(n) AS labels, count(n) AS cnt
        """,
        domain=domain,
    )
    by_type: dict[str, int] = {}
    total_nodes = 0
    async for rec in node_result:
        specific = [l for l in rec["labels"] if l != "Entity"]
        label = specific[0] if specific else "Entity"
        by_type[label] = by_type.get(label, 0) + rec["cnt"]
        total_nodes += rec["cnt"]

    edge_result = await session.run(
        """
        MATCH (a:Entity)-[r]->(b:Entity)
        WHERE $domain IS NULL OR a.domain = $domain OR b.domain = $domain
        RETURN count(r) AS cnt
        """,
        domain=domain,
    )
    edge_record = await edge_result.single()
    total_edges = edge_record["cnt"] if edge_record else 0

    return {"totalNodes": total_nodes, "totalEdges": total_edges, "byType": by_type}


async def upsert_knowledge_node(
    session: AsyncSession,
    knowledge_id: str,
    title: str,
    domain: str,
    knowledge_type: str,
    classification_level: str,
    status: str,
) -> None:
    """知识条目发布/更新时，把它作为一个 Knowledge 节点同步进图谱。"""
    await session.run(
        """
        MERGE (k:Entity:Knowledge {id: $id})
        SET k.name = $title,
            k.domain = $domain,
            k.type = 'Knowledge',
            k.knowledgeType = $knowledgeType,
            k.classificationLevel = $level,
            k.status = $status
        """,
        id=knowledge_id, title=title, domain=domain,
        knowledgeType=knowledge_type, level=classification_level, status=status,
    )


async def remove_knowledge_node(session: AsyncSession, knowledge_id: str) -> None:
    """知识条目被废弃/删除时，从图谱中移除对应节点（及其关系）。"""
    await session.run(
        "MATCH (k:Entity:Knowledge {id: $id}) DETACH DELETE k",
        id=knowledge_id,
    )


async def link_knowledge_to_entity(
    session: AsyncSession, knowledge_id: str, entity_id: str, relation: str = "DOCUMENTED_BY"
) -> bool:
    """把一条知识与某个已存在的本体实体（如某个故障模式）关联起来。"""
    if relation not in VALID_RELATION_TYPES:
        relation = "DOCUMENTED_BY"
    result = await session.run(
        f"""
        MATCH (e:Entity {{id: $entityId}}), (k:Entity:Knowledge {{id: $knowledgeId}})
        MERGE (e)-[r:{relation}]->(k)
        RETURN r
        """,
        entityId=entity_id, knowledgeId=knowledge_id,
    )
    record = await result.single()
    return record is not None


async def upsert_entity(
    session: AsyncSession,
    entity_id: str,
    name: str,
    entity_type: str,
    domain: Optional[str],
    properties: Optional[dict] = None,
) -> dict:
    if entity_type not in VALID_NODE_LABELS:
        raise ValueError(f"未知的实体类型: {entity_type}")
    extra = {k: v for k, v in (properties or {}).items() if isinstance(v, (str, int, float, bool))}
    result = await session.run(
        f"""
        MERGE (n:Entity:{entity_type} {{id: $id}})
        SET n.name = $name, n.domain = $domain, n.type = $type
        SET n += $extra
        RETURN n
        """,
        id=entity_id, name=name, domain=domain, type=entity_type, extra=extra,
    )
    record = await result.single()
    return _node_to_dict(record["n"])


async def create_relation(session: AsyncSession, source_id: str, target_id: str, relation: str) -> bool:
    if relation not in VALID_RELATION_TYPES:
        raise ValueError(f"未知的关系类型: {relation}")
    result = await session.run(
        f"""
        MATCH (a:Entity {{id: $source}}), (b:Entity {{id: $target}})
        MERGE (a)-[r:{relation}]->(b)
        RETURN r
        """,
        source=source_id, target=target_id,
    )
    record = await result.single()
    return record is not None
