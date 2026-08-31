from contextlib import asynccontextmanager

from fastapi import FastAPI

from .config import settings
from .db import TripRecord  # noqa: F401 — ensures model is registered before init_db
from .db.base import create_db_engine, create_session_factory, init_db
from .routers.trips import router as trips_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = create_db_engine(settings.database_url)
    await init_db(engine)
    app.state.session_factory = create_session_factory(engine)
    app.state.engine = engine
    yield
    await engine.dispose()


app = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)

app.include_router(trips_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": settings.app_name}
