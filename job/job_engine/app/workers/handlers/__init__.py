# app/workers/handlers/__init__.py
from app.models.job import JobType
from app.workers.handlers.email_handler import handle_email
from app.workers.handlers.ai_handler import handle_ai_task
from app.workers.handlers.data_cleaning_handler import handle_data_cleaning

HANDLER_MAP = {
    JobType.EMAIL: handle_email,
    JobType.AI_TASK: handle_ai_task,
    JobType.DATA_CLEANING: handle_data_cleaning,
}
