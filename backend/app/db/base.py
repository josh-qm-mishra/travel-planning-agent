from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def create_db_engine(url: str) -> AsyncEngine:
    """Create an async SQLAlchemy engine.

    SQLite gets StaticPool so all connections share the same in-memory database.
    """
    kwargs: dict = {}
    if "sqlite" in url:
        from sqlalchemy.pool import StaticPool

        kwargs["connect_args"] = {"check_same_thread": False}
        kwargs["poolclass"] = StaticPool
    return create_async_engine(url, **kwargs)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def init_db(engine: AsyncEngine) -> None:
    """Create all tables declared on Base.metadata.

    Used for development (SQLite) and tests.  Production databases should be
    managed exclusively through Alembic migrations (``alembic upgrade head``).
    This function remains idempotent (create_all skips existing tables) so it
    is safe to call against an already-migrated PostgreSQL database during the
    transition period, but it is NOT a replacement for proper migrations.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
