import asyncio
import logging

import aio_pika
from app.config import get_settings

logger = logging.getLogger(__name__)

rabbitmq_connection: aio_pika.RobustConnection | None = None
rabbitmq_channel: aio_pika.RobustChannel | None = None


async def init_rabbitmq():
    global rabbitmq_connection, rabbitmq_channel
    settings = get_settings()
    for attempt in range(10):
        try:
            rabbitmq_connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
            rabbitmq_channel = await rabbitmq_connection.channel()
            await rabbitmq_channel.set_qos(prefetch_count=10)

            await rabbitmq_channel.declare_queue(
                settings.RABBITMQ_INGESTION_QUEUE,
                durable=True,
                arguments={
                    "x-dead-letter-exchange": "",
                    "x-dead-letter-routing-key": settings.RABBITMQ_DLQ,
                },
            )
            await rabbitmq_channel.declare_queue(settings.RABBITMQ_DLQ, durable=True)
            logger.info("RabbitMQ connected successfully")
            return
        except Exception as e:
            logger.warning(f"RabbitMQ connection attempt {attempt + 1}/10 failed: {e}")
            await asyncio.sleep(3)
    logger.error("Failed to connect to RabbitMQ after 10 attempts, continuing without it")


async def close_rabbitmq():
    global rabbitmq_connection
    if rabbitmq_connection:
        await rabbitmq_connection.close()


def get_rabbitmq_channel() -> aio_pika.RobustChannel:
    return rabbitmq_channel