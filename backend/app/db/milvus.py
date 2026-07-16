import asyncio
import logging

from pymilvus import MilvusClient
from app.config import get_settings

logger = logging.getLogger(__name__)

milvus_client: MilvusClient | None = None


async def init_milvus():
    global milvus_client
    settings = get_settings()
    for attempt in range(10):
        try:
            milvus_client = MilvusClient(
                uri=f"http://{settings.MILVUS_HOST}:{settings.MILVUS_PORT}",
            )
            collection_name = settings.MILVUS_COLLECTION
            existing = milvus_client.list_collections()
            if collection_name not in existing:
                milvus_client.create_collection(
                    collection_name=collection_name,
                    dimension=settings.EMBEDDING_DIMENSION,
                    metric_type="COSINE",
                    auto_id=True,
                )
            logger.info("Milvus connected successfully")
            return
        except Exception as e:
            logger.warning(f"Milvus connection attempt {attempt + 1}/10 failed: {e}")
            milvus_client = None
            await asyncio.sleep(3)
    logger.error("Failed to connect to Milvus after 10 attempts, continuing without it")


async def close_milvus():
    global milvus_client
    if milvus_client:
        milvus_client.close()


def get_milvus_client() -> MilvusClient:
    return milvus_client