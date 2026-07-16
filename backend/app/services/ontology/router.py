import json
import logging
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import SecurityContext
from app.core.exceptions import ResourceNotFoundException, ServiceUnavailableException
from app.db.neo4j import get_neo4j_session
from app.db.postgresql import get_db
from app.middleware.auth import get_current_user, require_role
from app.models.models import AuditLog, OntologyChangeRequest, OntologyVersion
from app.schemas.common import ApiResponse
from app.services.ontology import graph_service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["本体与图谱"])

# PHM 领域核心本体的元模型定义（类与关系类型）。这是相对稳定的领域知识建模，
# 不属于图实例数据，因此维护为代码内常量而非存 Neo4j；图谱节点/关系的真实统计数据
# 则通过 Neo4j 实时查询获得，见下方 get_ontology_classes / get_graph_stats。
DEFAULT_CLASSES = [
    {"className": "Equipment", "labelZh": "装备", "properties": "id, name, model, domain, level"},
    {"className": "Component", "labelZh": "部件", "properties": "id, name, parent_id, type"},
    {"className": "FailureMode", "labelZh": "故障模式", "properties": "id, mechanism, severity"},
    {"className": "Symptom", "labelZh": "征兆", "properties": "id, parameter, detection_method"},
    {"className": "DiagnosisMethod", "labelZh": "诊断方法", "properties": "id, principle"},
    {"className": "HealthState", "labelZh": "健康状态", "properties": "id, threshold_definition"},
    {"className": "RULModel", "labelZh": "寿命预测模型", "properties": "id, applicable_type"},
    {"className": "MaintenanceStrategy", "labelZh": "维修策略", "properties": "id, description"},
]

DEFAULT_RELATIONS = [
    {"name": "BELONGS_TO", "domain": "Component", "range": "Equipment"},
    {"name": "OCCURS_IN", "domain": "FailureMode", "range": "Component"},
    {"name": "MANIFESTS_AS", "domain": "FailureMode", "range": "Symptom"},
    {"name": "LEADS_TO", "domain": "FailureMode", "range": "FailureMode"},
    {"name": "RESOLVED_BY", "domain": "FailureMode", "range": "MaintenanceStrategy"},
    {"name": "DETECTED_BY", "domain": "Symptom", "range": "DiagnosisMethod"},
    {"name": "APPLIES_MODEL", "domain": "Component", "range": "RULModel"},
    {"name": "DOCUMENTED_BY", "domain": "*", "range": "Knowledge"},
]


class OntologyChangeSubmitRequest(BaseModel):
    domain: str
    changeDescription: str
    classes: Optional[list[dict]] = None
    relations: Optional[list[dict]] = None


class OntologyPublishRequest(BaseModel):
    version: str
    comment: Optional[str] = None
    publisher_id: str

    model_config = {"populate_by_name": True}


class EntityUpsertRequest(BaseModel):
    id: str
    name: str
    type: str
    domain: Optional[str] = None
    properties: Optional[dict] = None


class RelationCreateRequest(BaseModel):
    source_id: str
    target_id: str
    relation: str


def _neo4j_unavailable(exc: Exception):
    logger.exception("Neo4j query failed")
    raise ServiceUnavailableException("图数据库暂不可用，请稍后重试") from exc


@router.get("/ontology/schema", response_model=ApiResponse)
async def get_ontology_schema(domain: str = Query(None), ctx: SecurityContext = Depends(get_current_user)):
    return ApiResponse(data={"domain": domain, "classes": DEFAULT_CLASSES, "relations": DEFAULT_RELATIONS})


@router.get("/ontology/classes", response_model=ApiResponse)
async def get_ontology_classes(
    domain: str = Query(None),
    session=Depends(get_neo4j_session),
    ctx: SecurityContext = Depends(get_current_user),
):
    try:
        stats = await graph_service.get_graph_stats(session, domain)
    except Exception as exc:
        logger.warning("Falling back to schema-only class list (Neo4j unavailable): %s", exc)
        stats = {"byType": {}}
    enriched = [{**c, "instanceCount": stats["byType"].get(c["className"], 0)} for c in DEFAULT_CLASSES]
    return ApiResponse(data=enriched)


@router.get("/ontology/relations", response_model=ApiResponse)
async def get_ontology_relations(domain: str = Query(None), ctx: SecurityContext = Depends(get_current_user)):
    return ApiResponse(data=DEFAULT_RELATIONS)


@router.post("/ontology/change-request", response_model=ApiResponse)
async def submit_ontology_change(
    req: OntologyChangeSubmitRequest,
    db: AsyncSession = Depends(get_db),
    ctx: SecurityContext = Depends(get_current_user),
):
    change_id = f"OC{uuid4().hex[:8].upper()}"
    change = OntologyChangeRequest(
        id=change_id,
        domain=req.domain,
        change_description=req.changeDescription,
        classes_json=json.dumps(req.classes, ensure_ascii=False) if req.classes else None,
        relations_json=json.dumps(req.relations, ensure_ascii=False) if req.relations else None,
        submitter_id=ctx.user_id,
    )
    db.add(change)
    db.add(AuditLog(
        id=f"AL{uuid4().hex[:12]}", user_id=ctx.user_id, action="ontology_change_request",
        resource_type="ontology", resource_id=change_id, detail=req.changeDescription,
    ))
    await db.commit()
    return ApiResponse(data={"changeId": change_id, "status": "pending"})


@router.get("/ontology/change-requests", response_model=ApiResponse)
async def list_ontology_changes(
    status: str = Query(None),
    db: AsyncSession = Depends(get_db),
    ctx: SecurityContext = Depends(get_current_user),
):
    stmt = select(OntologyChangeRequest).order_by(OntologyChangeRequest.created_at.desc())
    if status:
        stmt = stmt.where(OntologyChangeRequest.status == status)
    result = await db.execute(stmt)
    items = [
        {
            "changeId": c.id, "domain": c.domain, "changeDescription": c.change_description,
            "submitterId": c.submitter_id, "status": c.status, "createdAt": c.created_at.isoformat(),
        }
        for c in result.scalars().all()
    ]
    return ApiResponse(data=items)


@router.post("/ontology/publish", response_model=ApiResponse)
async def publish_ontology(
    req: OntologyPublishRequest,
    db: AsyncSession = Depends(get_db),
    ctx: SecurityContext = Depends(require_role("admin", "expert")),
):
    existing = await db.execute(select(OntologyVersion).where(OntologyVersion.version == req.version))
    if existing.scalar_one_or_none() is not None:
        from app.core.exceptions import ConflictException
        raise ConflictException(f"版本号 {req.version} 已存在")

    version_row = OntologyVersion(
        id=f"OV{uuid4().hex[:8].upper()}", version=req.version, comment=req.comment, publisher_id=req.publisher_id,
    )
    db.add(version_row)
    db.add(AuditLog(
        id=f"AL{uuid4().hex[:12]}", user_id=req.publisher_id, action="ontology_publish",
        resource_type="ontology_version", resource_id=version_row.id, detail=req.comment or "",
    ))
    await db.commit()
    return ApiResponse(data={"version": req.version, "status": "published", "publishedAt": version_row.published_at.isoformat()})


@router.get("/ontology/versions", response_model=ApiResponse)
async def list_ontology_versions(db: AsyncSession = Depends(get_db), ctx: SecurityContext = Depends(get_current_user)):
    result = await db.execute(select(OntologyVersion).order_by(OntologyVersion.published_at.desc()))
    versions = [
        {"version": v.version, "comment": v.comment, "publisherId": v.publisher_id, "publishedAt": v.published_at.isoformat()}
        for v in result.scalars().all()
    ]
    return ApiResponse(data=versions)


@router.get("/graph/stats", response_model=ApiResponse)
async def get_graph_stats(
    domain: str = Query(None),
    session=Depends(get_neo4j_session),
    ctx: SecurityContext = Depends(get_current_user),
):
    try:
        stats = await graph_service.get_graph_stats(session, domain)
    except Exception as exc:
        _neo4j_unavailable(exc)
    return ApiResponse(data=stats)


@router.get("/graph/search", response_model=ApiResponse)
async def search_graph(
    q: str = Query(..., min_length=1),
    domain: str = Query(None),
    limit: int = Query(20, ge=1, le=100),
    session=Depends(get_neo4j_session),
    ctx: SecurityContext = Depends(get_current_user),
):
    try:
        results = await graph_service.search_entities(session, q, domain, limit)
    except Exception as exc:
        _neo4j_unavailable(exc)
    return ApiResponse(data=results)


@router.get("/graph/entity/{entity_id}", response_model=ApiResponse)
async def get_entity(
    entity_id: str,
    session=Depends(get_neo4j_session),
    ctx: SecurityContext = Depends(get_current_user),
):
    try:
        entity = await graph_service.get_entity_detail(session, entity_id)
    except Exception as exc:
        _neo4j_unavailable(exc)
    if entity is None:
        raise ResourceNotFoundException(f"图谱实体 {entity_id} 不存在")
    return ApiResponse(data={
        "entityId": entity["id"], "name": entity["name"], "type": entity["type"],
        "domain": entity["domain"], "relations": entity["relations"],
    })


@router.post("/graph/entity", response_model=ApiResponse)
async def upsert_entity(
    req: EntityUpsertRequest,
    session=Depends(get_neo4j_session),
    ctx: SecurityContext = Depends(get_current_user),
):
    try:
        node = await graph_service.upsert_entity(session, req.id, req.name, req.type, req.domain, req.properties)
    except ValueError as exc:
        from app.core.exceptions import BusinessException
        raise BusinessException(code=40001, message=str(exc)) from exc
    except Exception as exc:
        _neo4j_unavailable(exc)
    return ApiResponse(data=node)


@router.post("/graph/relation", response_model=ApiResponse)
async def create_relation(
    req: RelationCreateRequest,
    session=Depends(get_neo4j_session),
    ctx: SecurityContext = Depends(get_current_user),
):
    try:
        ok = await graph_service.create_relation(session, req.source_id, req.target_id, req.relation)
    except ValueError as exc:
        from app.core.exceptions import BusinessException
        raise BusinessException(code=40001, message=str(exc)) from exc
    except Exception as exc:
        _neo4j_unavailable(exc)
    if not ok:
        raise ResourceNotFoundException("源节点或目标节点不存在")
    return ApiResponse(data={"sourceId": req.source_id, "targetId": req.target_id, "relation": req.relation})


@router.post("/graph/path-query", response_model=ApiResponse)
async def path_query(
    req: dict,
    session=Depends(get_neo4j_session),
    ctx: SecurityContext = Depends(get_current_user),
):
    from_entity = req.get("from") or req.get("fromEntity") or req.get("source")
    to_entity = req.get("to") or req.get("toEntity") or req.get("target")
    max_hops = int(req.get("maxHops", 6))
    if not from_entity or not to_entity:
        from app.core.exceptions import BusinessException
        raise BusinessException(code=40001, message="需要提供 from 和 to 两个实体")
    try:
        result = await graph_service.path_query(session, from_entity, to_entity, max_hops)
    except Exception as exc:
        _neo4j_unavailable(exc)
    return ApiResponse(data=result)


@router.get("/graph/subgraph", response_model=ApiResponse)
async def get_subgraph(
    center_entity: str = Query(None, alias="centerEntity"),
    depth: int = Query(2, ge=1, le=5),
    domain: str = Query(None),
    session=Depends(get_neo4j_session),
    ctx: SecurityContext = Depends(get_current_user),
):
    try:
        subgraph = await graph_service.get_subgraph(session, center_entity, depth, domain)
    except Exception as exc:
        _neo4j_unavailable(exc)
    return ApiResponse(data=subgraph)
