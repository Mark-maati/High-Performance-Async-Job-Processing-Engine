# app/redis_client.py
import json
import redis.asyncio as redis
from app.config import get_settings
from contextlib import asynccontextmanager
from typing import Any

settings = get_settings()

_redis_pool: redis.Redis | None = None


async def get_redis() -> redis.Redis | None:
    global _redis_pool
    if not settings.USE_REDIS:
        return None
    if _redis_pool is None:
        _redis_pool = redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            max_connections=20,
        )
    return _redis_pool


async def close_redis():
    global _redis_pool
    if _redis_pool:
        await _redis_pool.close()
        _redis_pool = None


class RedisQueue:
    """Priority queue backed by Redis sorted sets."""

    QUEUE_KEY = "job_queue:priority"
    PROCESSING_KEY = "job_queue:processing"
    STATS_KEY = "job_stats"

    def __init__(self, client: redis.Redis):
        self.client = client

    async def enqueue(self, job_id: str, priority: int = 5):
        # Higher priority = lower score = dequeued first
        score = -priority
        await self.client.zadd(self.QUEUE_KEY, {job_id: score})

    async def dequeue(self) -> str | None:
        # Atomically pop the highest-priority job
        result = await self.client.zpopmin(self.QUEUE_KEY, count=1)
        if result:
            job_id, _score = result[0]
            await self.client.sadd(self.PROCESSING_KEY, job_id)
            return job_id
        return None

    async def mark_done(self, job_id: str):
        await self.client.srem(self.PROCESSING_KEY, job_id)

    async def queue_length(self) -> int:
        return await self.client.zcard(self.QUEUE_KEY)

    async def processing_count(self) -> int:
        return await self.client.scard(self.PROCESSING_KEY)

    async def remove(self, job_id: str):
        await self.client.zrem(self.QUEUE_KEY, job_id)
        await self.client.srem(self.PROCESSING_KEY, job_id)

    async def increment_stat(self, stat_name: str, amount: int = 1):
        await self.client.hincrby(self.STATS_KEY, stat_name, amount)

    async def get_stats(self) -> dict:
        return await self.client.hgetall(self.STATS_KEY) or {}

    async def publish_event(self, event_type: str, data: dict):
        message = json.dumps({"event": event_type, **data})
        await self.client.publish("job_events", message)
