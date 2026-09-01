"""Tests for /health and /ready endpoints."""
import pytest
from unittest.mock import AsyncMock, patch
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from app.db.base import init_db
from app.db.deps import get_db
from app.main import app

client = TestClient(app)


def test_health_status_code():
    response = client.get("/health")
    assert response.status_code == 200


def test_health_response_body():
    response = client.get("/health")
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "travel-planning-agent"


def test_app_is_configured():
    assert app.title == "travel-planning-agent"


# ---------------------------------------------------------------------------
# /ready
# ---------------------------------------------------------------------------


@pytest.fixture
async def ready_client():
    """AsyncClient with isolated SQLite DB for /ready tests."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    await init_db(engine)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _override_get_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.pop(get_db, None)
    await engine.dispose()


@pytest.mark.anyio
async def test_ready_returns_200_when_db_reachable(ready_client):
    resp = await ready_client.get("/ready")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"
    assert resp.json()["database"] == "ok"


@pytest.mark.anyio
async def test_ready_returns_503_when_db_execute_fails():
    """When the DB session raises, /ready should return 503."""
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(side_effect=OSError("connection refused"))
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    async def _broken_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = _broken_get_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/ready")
        assert resp.status_code == 503
        assert resp.json()["status"] == "unavailable"
    finally:
        app.dependency_overrides.pop(get_db, None)
