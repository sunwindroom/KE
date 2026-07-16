import logging

from neo4j import AsyncGraphDatabase, AsyncDriver
from app.config import get_settings

driver: AsyncDriver | None = None


async def init_neo4j():
    global driver
    settings = get_settings()
    driver = AsyncGraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
    )
    try:
        from app.services.ontology.graph_service import ensure_constraints
        async with driver.session(database=settings.NEO4J_DATABASE) as session:
            await ensure_constraints(session)
    except Exception:
        logging.getLogger(__name__).exception(
            "Failed to ensure Neo4j constraints on startup (server may not be reachable yet)"
        )


async def close_neo4j():
    global driver
    if driver:
        await driver.close()


async def get_neo4j_session():
    settings = get_settings()
    async with driver.session(database=settings.NEO4J_DATABASE) as session:
        yield session