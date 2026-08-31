from typing import AsyncGenerator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession


async def get_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a database session from the app's session factory."""
    async with request.app.state.session_factory() as session:
        yield session
