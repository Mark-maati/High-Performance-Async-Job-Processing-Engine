# app/main.py
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.database import init_db
from app.auth.router import router as auth_router
from app.api.jobs import router as jobs_router
from app.api.dashboard import router as dashboard_router
from app.workers.manager import worker_manager
from app.redis_client import close_redis

settings = get_settings()

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    await init_db()
    await worker_manager.start()
    logger.info("Application ready.")
    yield
    # Shutdown
    logger.info("Shutting down...")
    await worker_manager.stop()
    await close_redis()
    logger.info("Shutdown complete.")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

# Routers
app.include_router(auth_router)
app.include_router(jobs_router)
app.include_router(dashboard_router)


@app.get("/health")
async def health():
    from app.redis_client import get_redis
    redis_ok = False
    r = await get_redis()
    if r:
        try:
            await r.ping()
            redis_ok = True
        except Exception:
            pass
    return {
        "status": "healthy",
        "version": settings.APP_VERSION,
        "redis_connected": redis_ok,
        "max_workers": settings.MAX_WORKERS,
    }
