from minio import Minio
from app.config import get_settings

minio_client: Minio | None = None

BUCKETS = ["phm-documents", "phm-attachments", "phm-models", "phm-backups"]


async def init_minio():
    global minio_client
    settings = get_settings()
    minio_client = Minio(
        settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_SECURE,
    )
    for bucket in BUCKETS:
        if not minio_client.bucket_exists(bucket):
            minio_client.make_bucket(bucket)


async def close_minio():
    pass


def get_minio_client() -> Minio:
    return minio_client