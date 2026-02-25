# app/api/__init__.py
from app.api.jobs import router as jobs_router
from app.api.dashboard import router as dashboard_router

__all__ = ["jobs_router", "dashboard_router"]
