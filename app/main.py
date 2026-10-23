import logging
logger = logging.getLogger('MunimJi.main')
"""Munim Ji AI FastAPI application entrypoint."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import config
from app.database import init_db, migrate_legacy_data
from app.logging_config import setup_logging
from app.routes.auth import router as auth_router
from app.routes.chat import router as chat_router
from app.routes.customers import router as customers_router
from app.routes.health import router as health_router
from app.routes.mobile_api import router as mobile_router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Initialise logging and the database before serving requests."""
    setup_logging()
    init_db()
    migrate_legacy_data()
    yield


app = FastAPI(
    title="Munim Ji AI API",
    version="3.1.0",
    lifespan=lifespan,
)
# Initialize Sentry if configured
if getattr(config, "SENTRY_DSN", None):
    try:
        import sentry_sdk
        sentry_sdk.init(
            dsn=config.SENTRY_DSN,
            traces_sample_rate=0.1,
            environment=getattr(config, "ENV", "production"),
        )
        logger.info("Sentry monitoring initialized successfully.")
    except Exception as _se:
        logger.warning(f"Sentry init error: {_se}")


# Wildcard origins cannot be combined with credentials. In production the
# config validator requires an explicit allow-list.
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=not config.CORS_ALLOW_ALL,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# Public health endpoints.
app.include_router(health_router)

# Authenticated mobile API.
app.include_router(auth_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(customers_router, prefix="/api")
app.include_router(mobile_router, prefix="/api")

@app.on_event("startup")
async def _start_daily_backup_schedule():
    import asyncio
    async def _daily_backup_worker():
        while True:
            await asyncio.sleep(86400)  # Every 24 hours
            try:
                from app.services.backup import run_daily_backup
                await asyncio.to_thread(run_daily_backup)
                logger.info("Automatic daily backup completed successfully.")
            except Exception as _be:
                logger.error(f"Scheduled backup failed: {_be}")
    asyncio.create_task(_daily_backup_worker())
