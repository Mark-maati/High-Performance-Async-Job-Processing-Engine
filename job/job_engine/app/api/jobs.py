# app/api/jobs.py
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, and_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.job import Job, JobStatus, JobType
from app.models.user import User, UserRole
from app.schemas.job import (
    JobCreate, JobResponse, JobListResponse, JobStats, BulkJobCreate,
)
from app.auth.dependencies import get_current_user, RoleRequired
from app.redis_client import get_redis, RedisQueue

router = APIRouter(prefix="/jobs", tags=["Jobs"])


@router.post("", response_model=JobResponse, status_code=201)
async def create_job(
    data: JobCreate,
    user: User = Depends(RoleRequired(UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db),
):
    job = Job(
        name=data.name,
        job_type=data.job_type,
        priority=data.priority,
        payload=data.payload,
        max_retries=data.max_retries,
        scheduled_at=data.scheduled_at,
        created_by=user.username,
        status=JobStatus.QUEUED,
    )
    db.add(job)
    await db.flush()
    await db.refresh(job)

    # Enqueue in Redis
    r = await get_redis()
    if r:
        queue = RedisQueue(r)
        await queue.enqueue(str(job.id), job.priority)
        await queue.increment_stat("enqueued")

    return job


@router.post("/bulk", response_model=list[JobResponse], status_code=201)
async def create_bulk_jobs(
    data: BulkJobCreate,
    user: User = Depends(RoleRequired(UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db),
):
    jobs = []
    for item in data.jobs:
        job = Job(
            name=item.name,
            job_type=item.job_type,
            priority=item.priority,
            payload=item.payload,
            max_retries=item.max_retries,
            scheduled_at=item.scheduled_at,
            created_by=user.username,
            status=JobStatus.QUEUED,
        )
        db.add(job)
        jobs.append(job)

    await db.flush()
    for j in jobs:
        await db.refresh(j)

    r = await get_redis()
    if r:
        queue = RedisQueue(r)
        for j in jobs:
            await queue.enqueue(str(j.id), j.priority)
        await queue.increment_stat("enqueued", len(jobs))

    return jobs


@router.get("", response_model=JobListResponse)
async def list_jobs(
    status: JobStatus | None = None,
    job_type: JobType | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(Job)
    count_query = select(func.count(Job.id))

    if status:
        query = query.where(Job.status == status)
        count_query = count_query.where(Job.status == status)
    if job_type:
        query = query.where(Job.job_type == job_type)
        count_query = count_query.where(Job.job_type == job_type)

    total = (await db.execute(count_query)).scalar() or 0

    query = (
        query.order_by(Job.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(query)

    return JobListResponse(
        jobs=result.scalars().all(),
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/stats", response_model=JobStats)
async def get_job_stats(
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)

    # Status counts
    status_result = await db.execute(
        select(Job.status, func.count(Job.id)).group_by(Job.status)
    )
    status_counts = {row[0]: row[1] for row in status_result.all()}

    total = sum(status_counts.values())

    # Average duration of completed jobs
    avg_dur = await db.execute(
        select(func.avg(Job.duration_seconds)).where(
            Job.status == JobStatus.COMPLETED
        )
    )
    avg_duration = avg_dur.scalar()

    # Success rate
    completed = status_counts.get(JobStatus.COMPLETED, 0)
    failed = status_counts.get(JobStatus.FAILED, 0)
    finished = completed + failed
    success_rate = (completed / finished * 100) if finished > 0 else None

    # Recent activity
    from datetime import timedelta

    jobs_1h = (
        await db.execute(
            select(func.count(Job.id)).where(
                Job.created_at >= now - timedelta(hours=1)
            )
        )
    ).scalar() or 0

    jobs_24h = (
        await db.execute(
            select(func.count(Job.id)).where(
                Job.created_at >= now - timedelta(hours=24)
            )
        )
    ).scalar() or 0

    return JobStats(
        total_jobs=total,
        pending=status_counts.get(JobStatus.PENDING, 0),
        queued=status_counts.get(JobStatus.QUEUED, 0),
        running=status_counts.get(JobStatus.RUNNING, 0),
        completed=completed,
        failed=failed,
        retrying=status_counts.get(JobStatus.RETRYING, 0),
        cancelled=status_counts.get(JobStatus.CANCELLED, 0),
        avg_duration_seconds=round(avg_duration, 3) if avg_duration else None,
        success_rate=round(success_rate, 2) if success_rate else None,
        jobs_last_hour=jobs_1h,
        jobs_last_24h=jobs_24h,
    )


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: uuid.UUID,
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/{job_id}/cancel", response_model=JobResponse)
async def cancel_job(
    job_id: uuid.UUID,
    user: User = Depends(RoleRequired(UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Job).where(Job.id == job_id).with_for_update()
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status in (JobStatus.COMPLETED, JobStatus.CANCELLED):
        raise HTTPException(
            status_code=400, detail=f"Cannot cancel job in '{job.status.value}' state"
        )

    job.status = JobStatus.CANCELLED
    job.completed_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(job)

    r = await get_redis()
    if r:
        queue = RedisQueue(r)
        await queue.remove(str(job.id))

    return job


@router.post("/{job_id}/retry", response_model=JobResponse)
async def retry_job(
    job_id: uuid.UUID,
    user: User = Depends(RoleRequired(UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Job).where(Job.id == job_id).with_for_update()
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status not in (JobStatus.FAILED, JobStatus.CANCELLED):
        raise HTTPException(
            status_code=400, detail="Can only retry failed or cancelled jobs"
        )

    job.status = JobStatus.QUEUED
    job.attempt = 0
    job.error_message = None
    job.result = None
    job.started_at = None
    job.completed_at = None
    job.duration_seconds = None
    job.next_retry_at = None
    await db.flush()
    await db.refresh(job)

    r = await get_redis()
    if r:
        queue = RedisQueue(r)
        await queue.enqueue(str(job.id), job.priority)

    return job
