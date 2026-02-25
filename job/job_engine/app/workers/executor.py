# app/workers/executor.py
import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import async_session_factory
from app.models.job import Job, JobStatus
from app.workers.handlers import HANDLER_MAP
from app.redis_client import get_redis, RedisQueue

logger = logging.getLogger(__name__)
settings = get_settings()


class JobExecutor:
    """Executes a single job with timeout, error handling, and retry logic."""

    def __init__(self, worker_id: str):
        self.worker_id = worker_id

    async def execute(self, job_id: uuid.UUID) -> bool:
        async with async_session_factory() as db:
            job = await self._claim_job(db, job_id)
            if not job:
                return False

            handler = HANDLER_MAP.get(job.job_type)
            if not handler:
                await self._fail_job(db, job, f"No handler for type: {job.job_type}")
                return False

            try:
                result = await asyncio.wait_for(
                    handler(job.payload),
                    timeout=settings.JOB_TIMEOUT_SECONDS,
                )
                await self._complete_job(db, job, result)
                return True

            except asyncio.TimeoutError:
                await self._handle_failure(
                    db, job, f"Job timed out after {settings.JOB_TIMEOUT_SECONDS}s"
                )
                return False

            except Exception as e:
                await self._handle_failure(db, job, str(e))
                return False

    async def _claim_job(self, db: AsyncSession, job_id: uuid.UUID) -> Job | None:
        """Atomically claim job using SELECT ... FOR UPDATE SKIP LOCKED."""
        result = await db.execute(
            select(Job)
            .where(Job.id == job_id)
            .where(Job.status.in_([JobStatus.PENDING, JobStatus.QUEUED, JobStatus.RETRYING]))
            .with_for_update(skip_locked=True)
        )
        job = result.scalar_one_or_none()
        if not job:
            return None

        job.status = JobStatus.RUNNING
        job.started_at = datetime.now(timezone.utc)
        job.attempt += 1
        job.worker_id = self.worker_id
        await db.commit()
        await db.refresh(job)

        logger.info(
            f"[{self.worker_id}] Claimed job {job.id} "
            f"(attempt {job.attempt}/{job.max_retries})"
        )
        return job

    async def _complete_job(self, db: AsyncSession, job: Job, result: dict):
        now = datetime.now(timezone.utc)
        duration = (now - job.started_at).total_seconds() if job.started_at else None

        job.status = JobStatus.COMPLETED
        job.result = result
        job.completed_at = now
        job.duration_seconds = duration
        job.error_message = None
        await db.commit()

        logger.info(
            f"[{self.worker_id}] Job {job.id} completed in {duration:.2f}s"
        )

        # Update Redis stats
        r = await get_redis()
        if r:
            queue = RedisQueue(r)
            await queue.mark_done(str(job.id))
            await queue.increment_stat("completed")
            await queue.publish_event("job_completed", {
                "job_id": str(job.id),
                "duration": duration,
            })

    async def _handle_failure(self, db: AsyncSession, job: Job, error: str):
        """Decide whether to retry or permanently fail."""
        if job.attempt < job.max_retries:
            # Exponential backoff: 2^attempt seconds
            backoff = settings.RETRY_BACKOFF_BASE ** job.attempt
            job.status = JobStatus.RETRYING
            job.next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=backoff)
            job.error_message = f"Attempt {job.attempt} failed: {error}"
            await db.commit()

            logger.warning(
                f"[{self.worker_id}] Job {job.id} failed (attempt {job.attempt}), "
                f"retrying in {backoff:.1f}s: {error}"
            )

            # Re-enqueue in Redis
            r = await get_redis()
            if r:
                queue = RedisQueue(r)
                await queue.mark_done(str(job.id))
                await queue.increment_stat("retries")
        else:
            await self._fail_job(db, job, error)

    async def _fail_job(self, db: AsyncSession, job: Job, error: str):
        now = datetime.now(timezone.utc)
        job.status = JobStatus.FAILED
        job.error_message = error
        job.completed_at = now
        if job.started_at:
            job.duration_seconds = (now - job.started_at).total_seconds()
        await db.commit()

        logger.error(f"[{self.worker_id}] Job {job.id} permanently failed: {error}")

        r = await get_redis()
        if r:
            queue = RedisQueue(r)
            await queue.mark_done(str(job.id))
            await queue.increment_stat("failed")
            await queue.publish_event("job_failed", {
                "job_id": str(job.id),
                "error": error,
            })
