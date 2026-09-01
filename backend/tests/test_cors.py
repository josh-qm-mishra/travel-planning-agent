"""Tests for CORS middleware configuration."""
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


@pytest.mark.anyio
async def test_cors_allowed_origin_returns_header(client):
    """A request from an allowed origin gets an Allow-Origin header back."""
    response = await client.get(
        "/health",
        headers={"Origin": "http://localhost:3000"},
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"


@pytest.mark.anyio
async def test_cors_preflight_returns_200(client):
    """OPTIONS preflight for an allowed origin returns 200."""
    response = await client.options(
        "/trips",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"


@pytest.mark.anyio
async def test_cors_disallowed_origin_no_header(client):
    """A request from an unlisted origin does not receive an Allow-Origin header."""
    response = await client.get(
        "/health",
        headers={"Origin": "http://evil.example.com"},
    )
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.anyio
async def test_cors_localhost_3001_allowed(client):
    """Port 3001 is in the default allowed list."""
    response = await client.get(
        "/health",
        headers={"Origin": "http://localhost:3001"},
    )
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3001"
