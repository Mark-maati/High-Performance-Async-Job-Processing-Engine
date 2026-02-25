# app/schemas/job.py
import uuid
from datetime import datetime
from pydantic import BaseModel, Field
from app.models.job import JobStatus, JobType, JobPriority


class JobCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    job_type: JobType
    priority: int = Field(default=JobPriority.NORMAL, ge=0, le=20)
    payload: dict = Field(default_factory=dict)
    max_retries: int = Field(default=5, ge=0, le=20)
    scheduled_at: datetime | None = None


class JobResponse(BaseModel):
    id: uuid.UUID
    name: str
    job_type: JobType
    status: JobStatus
    priority: int
    payload: dict
    result: dict | None
    error_message: str | None
    attempt: int
    max_retries: int
    next_retry_at: datetime | None
    created_at: datetime
    scheduled_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    duration_seconds: float | None
    created_by: str | None
    worker_id: str | None

    model_config = {"from_attributes": True}


class JobListResponse(BaseModel):
    jobs: list[JobResponse]
    total: int
    page: int
    page_size: int


class JobStats(BaseModel):
    total_jobs: int
    pending: int
    queued: int
    running: int
    completed: int
    failed: int
    retrying: int
    cancelled: int
    avg_duration_seconds: float | None
    success_rate: float | None
    jobs_last_hour: int
    jobs_last_24h: int


class BulkJobCreate(BaseModel):
    jobs: list[JobCreate] = Field(..., min_length=1, max_length=100)
