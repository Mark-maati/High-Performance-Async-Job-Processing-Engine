# app/api/dashboard.py
import asyncio
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.job import Job, JobStatus, JobType
from app.redis_client import get_redis, RedisQueue

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])
templates = Jinja2Templates(directory="templates")


@router.get("", response_class=HTMLResponse)
async def dashboard_page(request: Request, db: AsyncSession = Depends(get_db)):
    now = datetime.now(timezone.utc)

    # Status breakdown
    status_result = await db.execute(
        select(Job.status, func.count(Job.id)).group_by(Job.status)
    )
    status_counts = {row[0].value: row[1] for row in status_result.all()}

    # Type breakdown
    type_result = await db.execute(
        select(Job.job_type, func.count(Job.id)).group_by(Job.job_type)
    )
    type_counts = {row[0].value: row[1] for row in type_result.all()}

    # Throughput: jobs completed per hour (last 12 hours)
    throughput = []
    for i in range(12):
        hour_start = now - timedelta(hours=i + 1)
        hour_end = now - timedelta(hours=i)
        count = (
            await db.execute(
                select(func.count(Job.id)).where(
                    and_(
                        Job.completed_at >= hour_start,
                        Job.completed_at < hour_end,
                        Job.status == JobStatus.COMPLETED,
                    )
                )
            )
        ).scalar() or 0
        throughput.append({"hour": hour_start.strftime("%H:%M"), "count": count})
    throughput.reverse()

    # Recent jobs
    recent = await db.execute(
        select(Job).order_by(Job.created_at.desc()).limit(20)
    )
    recent_jobs = recent.scalars().all()

    # Average duration
    avg_dur = (
        await db.execute(
            select(func.avg(Job.duration_seconds)).where(
                Job.status == JobStatus.COMPLETED
            )
        )
    ).scalar()

    # Redis queue info
    redis_info = {}
    r = await get_redis()
    if r:
        queue = RedisQueue(r)
        redis_info = {
            "queue_length": await queue.queue_length(),
            "processing": await queue.processing_count(),
            "stats": await queue.get_stats(),
        }

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "status_counts": status_counts,
            "type_counts": type_counts,
            "throughput": throughput,
            "recent_jobs": recent_jobs,
            "avg_duration": round(avg_dur, 2) if avg_dur else "N/A",
            "redis_info": redis_info,
            "now": now.strftime("%Y-%m-%d %H:%M:%S UTC"),
        },
    )
