import json
import asyncio
from typing import Optional
from uuid import UUID
import logging
logger = logging.getLogger(__name__)

try:
    import redis.asyncio as aioredis
except ImportError:
    import redis as aioredis

from app.core.config import settings

redis_client = None

async def init_redis():
    global redis_client
    redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    await redis_client.ping()
    return redis_client

async def close_redis():
    global redis_client
    if redis_client:
        await redis_client.aclose()

def get_redis():
    return redis_client
