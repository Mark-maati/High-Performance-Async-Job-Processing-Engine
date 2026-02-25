# app/workers/manager.py
import asyncio
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, and_

from app.config import get_settings
from app.database import async_session_factory
from app.models.job import Job, JobStatus
from app.redis_client import get_redis, RedisQueue
from app.workers.executor import JobExecutor

logger = logging.getLogger(__name__)
settings = get_settings()


class WorkerManager:
    """
    Manages a pool of async workers that pull jobs from
    Redis (fast path) or PostgreSQL (fallback).
    """

    def __init__(self):
        self.manager_id = f"mgr-{uuid.uuid4().hex[:8]}"
        self.semaphore = asyncio.Semaphore(settings.MAX_WORKERS)
        self._running = False
        self._active_tasks: set[asyncio.Task] = set()
        self._poll_task: asyncio.Task | None = None
        self._retry_task: asyncio.Task | None = None

    async def start(self):
        self._running = True
        logger.info(
            f"[{self.manager_id}] Starting worker manager "
            f"(max_workers={settings.MAX_WORKERS})"
        )
        self._poll_task = asyncio.create_task(self._poll_loop())
        self._retry_task = asyncio.create_task(self._retry_loop())

    async def stop(self):
        self._running = False
        logger.info(f"[{self.manager_id}] Stopping worker manager...")

        if self._poll_task:
            self._poll_task.cancel()
        if self._retry_task:
            self._retry_task.cancel()

        # Wait for active tasks to complete
        if self._active_tasks:
            logger.info(f"Waiting for {len(self._active_tasks)} active tasks...")
            await asyncio.gather(*self._active_tasks, return_exceptions=True)

        logger.info(f"[{self.manager_id}] Worker manager stopped.")

    async def _poll_loop(self):
        """Main loop: dequeue jobs from Redis or poll PostgreSQL."""
        while self._running:
            try:
                job_id = await self._dequeue_job()
                if job_id:
                    await self.semaphore.acquire()
                    task = asyncio.create_task(self._run_job(job_id))
                    self._active_tasks.add(task)
                    task.add_done_callback(self._task_done)
                else:
                    await asyncio.sleep(settings.POLL_INTERVAL_SECONDS)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Poll loop error: {e}")
                await asyncio.sleep(2)

    async def _retry_loop(self):
        """Periodically check for jobs ready for retry."""
        while self._running:
            try:
                await asyncio.sleep(5)
                async with async_session_factory() as db:
                    now = datetime.now(timezone.utc)
                    result = await db.execute(
                        select(Job.id).where(
                            and_(
                                Job.status == JobStatus.RETRYING,
                                Job.next_retry_at <= now,
                            )
                        ).limit(settings.MAX_WORKERS)
                    )
                    retry_ids = [row[0] for row in result.all()]

                    for jid in retry_ids:
                        r = await get_redis()
                        if r:
                            queue = RedisQueue(r)
                            # Re-enqueue with original priority via DB lookup
                            job_result = await db.execute(
                                select(Job.priority).where(Job.id == jid)
                            )
                            priority = job_result.scalar() or 5
                            await queue.enqueue(str(jid), priority)
                        else:
                            # Without Redis, the poll loop will pick it up
                            stmt = (
                                select(Job)
                                .where(Job.id == jid)
                                .with_for_update(skip_locked=True)
                            )
                            job_row = await db.execute(stmt)
                            job_obj = job_row.scalar_one_or_none()
                            if job_obj:
                                job_obj.status = JobStatus.QUEUED
                                job_obj.next_retry_at = None

                    if retry_ids:
                        await db.commit()
                        logger.info(f"Re-queued {len(retry_ids)} retry jobs")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Retry loop error: {e}")

    async def _dequeue_job(self) -> uuid.UUID | None:
        """Try Redis first, fall back to PostgreSQL."""
        r = await get_redis()
        if r:
            queue = RedisQueue(r)
            job_id_str = await queue.dequeue()
            if job_id_str:
                return uuid.UUID(job_id_str)

        # Fallback: query PostgreSQL directly
        async with async_session_factory() as db:
            now = datetime.now(timezone.utc)
            result = await db.execute(
                select(Job.id)
                .where(
                    Job.status.in_([JobStatus.PENDING, JobStatus.QUEUED]),
                    (Job.scheduled_at.is_(None)) | (Job.scheduled_at <= now),
                )
                .order_by(Job.priority.desc(), Job.created_at.asc())
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            row = result.first()
            if row:
                return row[0]
        return None

    async def _run_job(self, job_id: uuid.UUID):
        worker_id = f"{self.manager_id}:w-{uuid.uuid4().hex[:6]}"
        executor = JobExecutor(worker_id)
        try:
            await executor.execute(job_id)
        except Exception as e:
            logger.error(f"Unhandled executor error for job {job_id}: {e}")

    def _task_done(self, task: asyncio.Task):
        self._active_tasks.discard(task)
        self.semaphore.release()
        if task.exception():
            logger.error(f"Task exception: {task.exception()}")


# Global instance
worker_manager = WorkerManager()
