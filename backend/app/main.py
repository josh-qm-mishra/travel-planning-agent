import logging
import logging.config
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .db import TripRecord  # noqa: F401 — ensures model is registered before init_db
from .db.base import create_db_engine, create_session_factory, init_db
from .db.deps import get_db
from .rate_limit import init_limiter
from .routers.trips import router as trips_router

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

_LOG_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
            "datefmt": "%Y-%m-%dT%H:%M:%S",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "default",
        },
    },
    "root": {
        "level": settings.log_level,
        "handlers": ["console"],
    },
    # Quieten noisy libraries.
    "loggers": {
        "httpx": {"level": "WARNING"},
        "httpcore": {"level": "WARNING"},
        "openai": {"level": "WARNING"},
        "sqlalchemy.engine": {"level": "WARNING"},
        "uvicorn.access": {"level": "WARNING"},
    },
}

logging.config.dictConfig(_LOG_CONFIG)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Application lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("startup service=%s debug=%s", settings.app_name, settings.debug)
    init_limiter(settings.rate_limit_per_minute, settings.rate_limit_per_hour)
    engine = create_db_engine(settings.database_url)
    await init_db(engine)
    app.state.session_factory = create_session_factory(engine)
    app.state.engine = engine
    logger.info("startup_complete database_ready=true")
    yield
    logger.info("shutdown service=%s", settings.app_name)
    await engine.dispose()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(trips_router)


# ---------------------------------------------------------------------------
# Health / readiness
# ---------------------------------------------------------------------------


@app.get("/health")
def health() -> dict:
    """Lightweight liveness probe — never touches the database or external APIs."""
    return {"status": "ok", "service": settings.app_name}


@app.get("/ready")
async def ready(response: Response, db: AsyncSession = Depends(get_db)) -> dict:
    """Readiness probe — verifies database connectivity.

    Returns 200 when the database is reachable, 503 otherwise.
    Suitable for use as a Kubernetes/load-balancer readiness check.
    Does NOT call OpenAI, Google, or any other paid external service.
    """
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "ready", "database": "ok"}
    except Exception as exc:
        logger.error("readiness_check_failed error=%s", exc)
        response.status_code = 503
        return {"status": "unavailable", "database": "error"}
