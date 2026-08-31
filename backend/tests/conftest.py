"""Shared pytest fixtures.

Key guarantee: _use_test_database patches settings.database_url to an
in-memory SQLite URL for every test in the session, so the app lifespan
never attempts to connect to a real PostgreSQL server during tests — even
if DATABASE_URL is present in the developer's .env file.
"""
import pytest
from unittest.mock import patch
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.db.base import Base, init_db


@pytest.fixture(autouse=True, scope="session")
def _use_test_database():
    """Override DATABASE_URL for the entire test session."""
    with patch.object(settings, "database_url", "sqlite+aiosqlite:///:memory:"):
        yield


@pytest.fixture
async def db_engine():
    """Fresh in-memory SQLite engine with all tables created."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    await init_db(engine)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(db_engine):
    """Async SQLAlchemy session bound to the test engine."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        yield session
