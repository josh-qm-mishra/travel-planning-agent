"""Tests for the /trips endpoints.

plan_trip and replan_trip are mocked throughout — no AI API calls are made.
Each test gets an isolated in-memory SQLite database via the client fixture.
"""
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import httpx2
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.agent.exceptions import MaxIterationsError, PlanningError, ValidationFailedError
from app.agent.models import AgentRunMetadata, ReplanResult, TripChangeSummary
from app.config import settings
from app.db.base import init_db
from app.db.deps import get_db
from app.db.repository import ConflictError
from app.main import app
from app.models.trip import Trip
from app.rate_limit import SlidingWindowLimiter, get_limiter


# ---------------------------------------------------------------------------
# Shared trip fixture
# ---------------------------------------------------------------------------

VALID_TRIP_DATA = {
    "destination": "Paris",
    "start_date": "2025-06-01",
    "end_date": "2025-06-01",
    "total_budget": None,
    "preferences": {
        "interests": [],
        "food_preferences": [],
        "pace": "moderate",
        "morning_preference": True,
        "walking_tolerance": "moderate",
    },
    "constraints": {
        "earliest_start_time": None,
        "latest_end_time": None,
        "maximum_budget": None,
    },
    "days": [
        {
            "date": "2025-06-01",
            "activities": [
                {
                    "name": "Eiffel Tower",
                    "location": "Champ de Mars, Paris",
                    "start_time": "09:00:00",
                    "end_time": "11:00:00",
                    "estimated_cost": 25.0,
                    "category": "sightseeing",
                    "locked": False,
                    "notes": None,
                },
                {
                    "name": "Lunch at Café",
                    "location": "Rue de Rivoli, Paris",
                    "start_time": "12:00:00",
                    "end_time": "13:00:00",
                    "estimated_cost": 20.0,
                    "category": "food",
                    "locked": False,
                    "notes": None,
                },
            ],
        }
    ],
}


def make_trip() -> Trip:
    return Trip(**VALID_TRIP_DATA)


def make_metadata(tools: int = 2) -> AgentRunMetadata:
    return AgentRunMetadata(
        tools_called=["geocode_location"] * tools,
        tool_call_count=tools,
        validation_attempts=1,
        success=True,
    )


def make_change_summary() -> TripChangeSummary:
    return TripChangeSummary(
        activities_added=1,
        activities_removed=0,
        activities_changed=0,
        affected_dates=[date(2025, 6, 1)],
        budget_difference=15.0,
        summary="1 added",
    )


# ---------------------------------------------------------------------------
# Unlimited rate limiter for tests
# ---------------------------------------------------------------------------

_UNLIMITED_LIMITER = SlidingWindowLimiter(per_minute=10_000, per_hour=100_000)


# ---------------------------------------------------------------------------
# Test client fixture with isolated DB
# ---------------------------------------------------------------------------


@pytest.fixture
async def client():
    """AsyncClient backed by an isolated in-memory SQLite database.

    The rate limiter is replaced with a high-limit stub so tests don't
    inadvertently trigger 429s.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    await init_db(engine)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_limiter] = lambda: _UNLIMITED_LIMITER
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_limiter, None)
    await engine.dispose()


# Default test client header (owner A)
_OWNER_A = {"X-Client-ID": "owner-a-test"}
_OWNER_B = {"X-Client-ID": "owner-b-test"}


# ---------------------------------------------------------------------------
# POST /trips
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_create_trip_returns_201(client):
    with patch("app.routers.trips.plan_trip", return_value=(make_trip(), make_metadata())):
        resp = await client.post("/trips", json={
            "destination": "Paris",
            "start_date": "2025-06-01",
            "end_date": "2025-06-01",
        }, headers=_OWNER_A)
    assert resp.status_code == 201


@pytest.mark.anyio
async def test_create_trip_response_has_id(client):
    with patch("app.routers.trips.plan_trip", return_value=(make_trip(), make_metadata())):
        resp = await client.post("/trips", json={
            "destination": "Paris",
            "start_date": "2025-06-01",
            "end_date": "2025-06-01",
        }, headers=_OWNER_A)
    data = resp.json()
    assert "id" in data
    assert len(data["id"]) == 36  # UUID string


@pytest.mark.anyio
async def test_create_trip_response_contains_trip(client):
    with patch("app.routers.trips.plan_trip", return_value=(make_trip(), make_metadata())):
        resp = await client.post("/trips", json={
            "destination": "Paris",
            "start_date": "2025-06-01",
            "end_date": "2025-06-01",
        }, headers=_OWNER_A)
    data = resp.json()
    assert data["trip"]["destination"] == "Paris"
    assert len(data["trip"]["days"]) == 1


@pytest.mark.anyio
async def test_create_trip_response_contains_agent_run(client):
    with patch("app.routers.trips.plan_trip", return_value=(make_trip(), make_metadata(tools=3))):
        resp = await client.post("/trips", json={
            "destination": "Paris",
            "start_date": "2025-06-01",
            "end_date": "2025-06-01",
        }, headers=_OWNER_A)
    data = resp.json()
    assert data["agent_run"]["tool_call_count"] == 3
    assert data["agent_run"]["success"] is True


@pytest.mark.anyio
async def test_create_trip_returns_502_on_planning_error(client):
    with patch("app.routers.trips.plan_trip", side_effect=PlanningError("API down")):
        resp = await client.post("/trips", json={
            "destination": "Paris",
            "start_date": "2025-06-01",
            "end_date": "2025-06-01",
        }, headers=_OWNER_A)
    assert resp.status_code == 502


@pytest.mark.anyio
async def test_create_trip_502_does_not_expose_internal_message(client):
    """Raw PlanningError text must not appear in the HTTP response body."""
    with patch(
        "app.routers.trips.plan_trip",
        side_effect=PlanningError("sk-secret-key quota exceeded internal detail"),
    ):
        resp = await client.post("/trips", json={
            "destination": "Paris",
            "start_date": "2025-06-01",
            "end_date": "2025-06-01",
        }, headers=_OWNER_A)
    assert resp.status_code == 502
    body = resp.text
    assert "sk-secret" not in body
    assert "quota exceeded" not in body
    assert "internal detail" not in body
    assert "traceback" not in body.lower()


@pytest.mark.anyio
async def test_create_trip_502_returns_stable_safe_message(client):
    with patch("app.routers.trips.plan_trip", side_effect=PlanningError("anything")):
        resp = await client.post("/trips", json={
            "destination": "Paris",
            "start_date": "2025-06-01",
            "end_date": "2025-06-01",
        }, headers=_OWNER_A)
    assert resp.json()["detail"] == "Trip planning failed. Please try again."


@pytest.mark.anyio
async def test_create_trip_returns_422_on_validation_failed(client):
    exc = ValidationFailedError("overlap found", failures=["schedule.overlap: ..."])
    with patch("app.routers.trips.plan_trip", side_effect=exc):
        resp = await client.post("/trips", json={
            "destination": "Paris",
            "start_date": "2025-06-01",
            "end_date": "2025-06-01",
        }, headers=_OWNER_A)
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_create_trip_returns_401_without_client_id(client):
    with patch("app.routers.trips.plan_trip", return_value=(make_trip(), make_metadata())):
        resp = await client.post("/trips", json={
            "destination": "Paris",
            "start_date": "2025-06-01",
            "end_date": "2025-06-01",
        })
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /trips/{id}
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_get_trip_returns_stored_trip(client):
    with patch("app.routers.trips.plan_trip", return_value=(make_trip(), make_metadata())):
        create_resp = await client.post("/trips", json={
            "destination": "Paris",
            "start_date": "2025-06-01",
            "end_date": "2025-06-01",
        }, headers=_OWNER_A)
    trip_id = create_resp.json()["id"]

    resp = await client.get(f"/trips/{trip_id}", headers=_OWNER_A)
    assert resp.status_code == 200
    assert resp.json()["id"] == trip_id
    assert resp.json()["trip"]["destination"] == "Paris"


@pytest.mark.anyio
async def test_get_trip_404_for_unknown_id(client):
    resp = await client.get("/trips/00000000-0000-0000-0000-000000000000", headers=_OWNER_A)
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_get_trip_404_detail(client):
    resp = await client.get("/trips/does-not-exist", headers=_OWNER_A)
    assert resp.json()["detail"] == "Trip not found"


@pytest.mark.anyio
async def test_get_trip_returns_401_without_client_id(client):
    resp = await client.get("/trips/any-id")
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_get_trip_404_for_different_owner(client):
    """Owner B cannot read a trip created by Owner A."""
    with patch("app.routers.trips.plan_trip", return_value=(make_trip(), make_metadata())):
        create_resp = await client.post("/trips", json={
            "destination": "Paris",
            "start_date": "2025-06-01",
            "end_date": "2025-06-01",
        }, headers=_OWNER_A)
    trip_id = create_resp.json()["id"]

    resp = await client.get(f"/trips/{trip_id}", headers=_OWNER_B)
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /trips
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_list_trips_empty(client):
    resp = await client.get("/trips", headers=_OWNER_A)
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.anyio
async def test_list_trips_returns_all(client):
    with patch("app.routers.trips.plan_trip", return_value=(make_trip(), make_metadata())):
        await client.post("/trips", json={
            "destination": "Paris",
            "start_date": "2025-06-01",
            "end_date": "2025-06-01",
        }, headers=_OWNER_A)
        await client.post("/trips", json={
            "destination": "Paris",
            "start_date": "2025-06-01",
            "end_date": "2025-06-01",
        }, headers=_OWNER_A)

    resp = await client.get("/trips", headers=_OWNER_A)
    assert resp.status_code == 200
    assert len(resp.json()) == 2


@pytest.mark.anyio
async def test_list_trips_each_has_id(client):
    with patch("app.routers.trips.plan_trip", return_value=(make_trip(), make_metadata())):
        await client.post("/trips", json={
            "destination": "Paris",
            "start_date": "2025-06-01",
            "end_date": "2025-06-01",
        }, headers=_OWNER_A)

    resp = await client.get("/trips", headers=_OWNER_A)
    for item in resp.json():
        assert "id" in item
        assert "trip" in item


@pytest.mark.anyio
async def test_list_trips_returns_401_without_client_id(client):
    resp = await client.get("/trips")
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_list_trips_excludes_other_owner(client):
    """Owner A's trips are not visible to Owner B and vice versa."""
    with patch("app.routers.trips.plan_trip", return_value=(make_trip(), make_metadata())):
        await client.post("/trips", json={
            "destination": "Paris",
            "start_date": "2025-06-01",
            "end_date": "2025-06-01",
        }, headers=_OWNER_A)
        await client.post("/trips", json={
            "destination": "Paris",
            "start_date": "2025-06-01",
            "end_date": "2025-06-01",
        }, headers=_OWNER_B)

    a_list = await client.get("/trips", headers=_OWNER_A)
    assert len(a_list.json()) == 1

    b_list = await client.get("/trips", headers=_OWNER_B)
    assert len(b_list.json()) == 1


# ---------------------------------------------------------------------------
# POST /trips/{id}/replan
# ---------------------------------------------------------------------------


async def _create_trip(client) -> str:
    with patch("app.routers.trips.plan_trip", return_value=(make_trip(), make_metadata())):
        resp = await client.post("/trips", json={
            "destination": "Paris",
            "start_date": "2025-06-01",
            "end_date": "2025-06-01",
        }, headers=_OWNER_A)
    return resp.json()["id"]


@pytest.mark.anyio
async def test_replan_returns_200(client):
    trip_id = await _create_trip(client)
    replan_result = ReplanResult(trip=make_trip(), change_summary=make_change_summary())
    with patch("app.routers.trips.replan_trip", return_value=replan_result):
        resp = await client.post(f"/trips/{trip_id}/replan", json={
            "change_request": "Add a museum visit"
        }, headers=_OWNER_A)
    assert resp.status_code == 200


@pytest.mark.anyio
async def test_replan_preserves_same_trip_id(client):
    trip_id = await _create_trip(client)
    replan_result = ReplanResult(trip=make_trip(), change_summary=make_change_summary())
    with patch("app.routers.trips.replan_trip", return_value=replan_result):
        resp = await client.post(f"/trips/{trip_id}/replan", json={
            "change_request": "Add a museum visit"
        }, headers=_OWNER_A)
    assert resp.json()["id"] == trip_id


@pytest.mark.anyio
async def test_replan_response_contains_change_summary(client):
    trip_id = await _create_trip(client)
    summary = make_change_summary()
    replan_result = ReplanResult(trip=make_trip(), change_summary=summary)
    with patch("app.routers.trips.replan_trip", return_value=replan_result):
        resp = await client.post(f"/trips/{trip_id}/replan", json={
            "change_request": "Add a museum visit"
        }, headers=_OWNER_A)
    data = resp.json()
    assert data["change_summary"]["activities_added"] == 1
    assert data["change_summary"]["summary"] == "1 added"


@pytest.mark.anyio
async def test_replan_persists_updated_trip(client):
    """After replan, GET /trips/{id} returns the updated trip."""
    updated_trip_data = {**VALID_TRIP_DATA, "destination": "London"}
    updated_trip = Trip(**updated_trip_data)

    trip_id = await _create_trip(client)
    replan_result = ReplanResult(trip=updated_trip, change_summary=make_change_summary())
    with patch("app.routers.trips.replan_trip", return_value=replan_result):
        await client.post(f"/trips/{trip_id}/replan", json={"change_request": "Move to London"}, headers=_OWNER_A)

    resp = await client.get(f"/trips/{trip_id}", headers=_OWNER_A)
    assert resp.json()["trip"]["destination"] == "London"


@pytest.mark.anyio
async def test_replan_updates_trip_in_list(client):
    """After replan, GET /trips reflects the updated trip."""
    updated_trip_data = {**VALID_TRIP_DATA, "destination": "Berlin"}
    updated_trip = Trip(**updated_trip_data)

    trip_id = await _create_trip(client)
    replan_result = ReplanResult(trip=updated_trip, change_summary=make_change_summary())
    with patch("app.routers.trips.replan_trip", return_value=replan_result):
        await client.post(f"/trips/{trip_id}/replan", json={"change_request": "Go to Berlin"}, headers=_OWNER_A)

    resp = await client.get("/trips", headers=_OWNER_A)
    destinations = [item["trip"]["destination"] for item in resp.json()]
    assert "Berlin" in destinations


@pytest.mark.anyio
async def test_replan_404_for_unknown_id(client):
    replan_result = ReplanResult(trip=make_trip(), change_summary=make_change_summary())
    with patch("app.routers.trips.replan_trip", return_value=replan_result):
        resp = await client.post("/trips/nonexistent-id/replan", json={
            "change_request": "Change something"
        }, headers=_OWNER_A)
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_replan_returns_502_on_planning_error(client):
    trip_id = await _create_trip(client)
    with patch("app.routers.trips.replan_trip", side_effect=PlanningError("LLM unavailable")):
        resp = await client.post(f"/trips/{trip_id}/replan", json={
            "change_request": "Change something"
        }, headers=_OWNER_A)
    assert resp.status_code == 502


@pytest.mark.anyio
async def test_replan_502_does_not_expose_internal_message(client):
    """Internal replan error detail must not appear in the HTTP response body."""
    trip_id = await _create_trip(client)
    with patch(
        "app.routers.trips.replan_trip",
        side_effect=PlanningError("OpenAI API key invalid sk-proj-abc123"),
    ):
        resp = await client.post(f"/trips/{trip_id}/replan", json={
            "change_request": "Change something"
        }, headers=_OWNER_A)
    assert resp.status_code == 502
    body = resp.text
    assert "sk-proj" not in body
    assert "OpenAI API key invalid" not in body


@pytest.mark.anyio
async def test_replan_502_returns_stable_safe_message(client):
    trip_id = await _create_trip(client)
    with patch("app.routers.trips.replan_trip", side_effect=PlanningError("anything")):
        resp = await client.post(f"/trips/{trip_id}/replan", json={
            "change_request": "Change something"
        }, headers=_OWNER_A)
    assert resp.json()["detail"] == "Trip replanning failed. Please try again."


@pytest.mark.anyio
async def test_replan_returns_422_on_validation_failed(client):
    trip_id = await _create_trip(client)
    exc = ValidationFailedError("still overlapping", failures=["schedule.overlap"])
    with patch("app.routers.trips.replan_trip", side_effect=exc):
        resp = await client.post(f"/trips/{trip_id}/replan", json={
            "change_request": "Change something"
        }, headers=_OWNER_A)
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_replan_passes_existing_trip_to_planner(client):
    """The existing Trip object is reconstructed from storage before replanning."""
    trip_id = await _create_trip(client)
    captured = {}

    async def capture_replan(existing_trip, change_request):
        captured["trip"] = existing_trip
        captured["request"] = change_request
        return ReplanResult(trip=make_trip(), change_summary=make_change_summary())

    with patch("app.routers.trips.replan_trip", side_effect=capture_replan):
        await client.post(f"/trips/{trip_id}/replan", json={"change_request": "Add dinner"}, headers=_OWNER_A)

    assert isinstance(captured["trip"], Trip)
    assert captured["trip"].destination == "Paris"
    assert captured["request"] == "Add dinner"


@pytest.mark.anyio
async def test_replan_returns_401_without_client_id(client):
    trip_id = await _create_trip(client)
    replan_result = ReplanResult(trip=make_trip(), change_summary=make_change_summary())
    with patch("app.routers.trips.replan_trip", return_value=replan_result):
        resp = await client.post(f"/trips/{trip_id}/replan", json={
            "change_request": "Change something"
        })
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_replan_404_for_different_owner(client):
    """Owner B cannot replan a trip created by Owner A."""
    trip_id = await _create_trip(client)
    replan_result = ReplanResult(trip=make_trip(), change_summary=make_change_summary())
    with patch("app.routers.trips.replan_trip", return_value=replan_result):
        resp = await client.post(f"/trips/{trip_id}/replan", json={
            "change_request": "Change something"
        }, headers=_OWNER_B)
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


@pytest.fixture
async def rate_limited_client():
    """Client whose limiter allows only 1 request per minute."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    await init_db(engine)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_db():
        async with factory() as session:
            yield session

    tight_limiter = SlidingWindowLimiter(per_minute=1, per_hour=100)
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_limiter] = lambda: tight_limiter
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_limiter, None)
    await engine.dispose()


@pytest.mark.anyio
async def test_create_trip_rate_limited_after_limit(rate_limited_client):
    """Second create request by same owner within a minute returns 429."""
    payload = {"destination": "Paris", "start_date": "2025-06-01", "end_date": "2025-06-01"}
    with patch("app.routers.trips.plan_trip", return_value=(make_trip(), make_metadata())):
        resp1 = await rate_limited_client.post("/trips", json=payload, headers=_OWNER_A)
    assert resp1.status_code == 201

    with patch("app.routers.trips.plan_trip", return_value=(make_trip(), make_metadata())):
        resp2 = await rate_limited_client.post("/trips", json=payload, headers=_OWNER_A)
    assert resp2.status_code == 429


@pytest.mark.anyio
async def test_rate_limit_has_retry_after_header(rate_limited_client):
    """429 response includes Retry-After header."""
    payload = {"destination": "Paris", "start_date": "2025-06-01", "end_date": "2025-06-01"}
    with patch("app.routers.trips.plan_trip", return_value=(make_trip(), make_metadata())):
        await rate_limited_client.post("/trips", json=payload, headers=_OWNER_A)
    with patch("app.routers.trips.plan_trip", return_value=(make_trip(), make_metadata())):
        resp = await rate_limited_client.post("/trips", json=payload, headers=_OWNER_A)
    assert resp.status_code == 429
    assert "retry-after" in resp.headers


@pytest.mark.anyio
async def test_rate_limit_is_per_owner(rate_limited_client):
    """Rate limit is independent per owner; Owner B not throttled by Owner A's requests."""
    payload = {"destination": "Paris", "start_date": "2025-06-01", "end_date": "2025-06-01"}
    with patch("app.routers.trips.plan_trip", return_value=(make_trip(), make_metadata())):
        r1 = await rate_limited_client.post("/trips", json=payload, headers=_OWNER_A)
    assert r1.status_code == 201

    with patch("app.routers.trips.plan_trip", return_value=(make_trip(), make_metadata())):
        r2 = await rate_limited_client.post("/trips", json=payload, headers=_OWNER_B)
    assert r2.status_code == 201


# ---------------------------------------------------------------------------
# Response shape sanity checks
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_response_has_timestamps(client):
    with patch("app.routers.trips.plan_trip", return_value=(make_trip(), make_metadata())):
        resp = await client.post("/trips", json={
            "destination": "Paris",
            "start_date": "2025-06-01",
            "end_date": "2025-06-01",
        }, headers=_OWNER_A)
    data = resp.json()
    assert "created_at" in data
    assert "updated_at" in data


@pytest.mark.anyio
async def test_response_has_version(client):
    with patch("app.routers.trips.plan_trip", return_value=(make_trip(), make_metadata())):
        resp = await client.post("/trips", json={
            "destination": "Paris",
            "start_date": "2025-06-01",
            "end_date": "2025-06-01",
        }, headers=_OWNER_A)
    assert resp.json()["version"] == 1


@pytest.mark.anyio
async def test_replan_increments_version(client):
    trip_id = await _create_trip(client)
    replan_result = ReplanResult(trip=make_trip(), change_summary=make_change_summary())
    with patch("app.routers.trips.replan_trip", return_value=replan_result):
        resp = await client.post(f"/trips/{trip_id}/replan", json={
            "change_request": "Add a museum visit"
        }, headers=_OWNER_A)
    assert resp.json()["version"] == 2


@pytest.mark.anyio
async def test_replan_with_correct_expected_version_succeeds(client):
    trip_id = await _create_trip(client)
    replan_result = ReplanResult(trip=make_trip(), change_summary=make_change_summary())
    with patch("app.routers.trips.replan_trip", return_value=replan_result):
        resp = await client.post(f"/trips/{trip_id}/replan", json={
            "change_request": "Add a museum visit",
            "expected_version": 1,
        }, headers=_OWNER_A)
    assert resp.status_code == 200
    assert resp.json()["version"] == 2


@pytest.mark.anyio
async def test_replan_with_stale_version_returns_409(client):
    trip_id = await _create_trip(client)
    replan_result = ReplanResult(trip=make_trip(), change_summary=make_change_summary())

    # First replan advances version to 2.
    with patch("app.routers.trips.replan_trip", return_value=replan_result):
        await client.post(f"/trips/{trip_id}/replan", json={
            "change_request": "First change",
            "expected_version": 1,
        }, headers=_OWNER_A)

    # Second replan with stale version=1 must be rejected.
    with patch("app.routers.trips.replan_trip", return_value=replan_result):
        resp = await client.post(f"/trips/{trip_id}/replan", json={
            "change_request": "Stale change",
            "expected_version": 1,
        }, headers=_OWNER_A)
    assert resp.status_code == 409


@pytest.mark.anyio
async def test_replan_409_detail_is_user_safe(client):
    trip_id = await _create_trip(client)
    replan_result = ReplanResult(trip=make_trip(), change_summary=make_change_summary())
    with patch("app.routers.trips.replan_trip", return_value=replan_result):
        await client.post(f"/trips/{trip_id}/replan", json={
            "change_request": "First change",
            "expected_version": 1,
        }, headers=_OWNER_A)
    with patch("app.routers.trips.replan_trip", return_value=replan_result):
        resp = await client.post(f"/trips/{trip_id}/replan", json={
            "change_request": "Stale change",
            "expected_version": 1,
        }, headers=_OWNER_A)
    detail = resp.json()["detail"]
    # Should not expose DB internals.
    assert "version" not in detail.lower() or "refresh" in detail.lower()
    assert "Refresh" in detail or "refresh" in detail


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_create_trip_rejects_destination_too_long(client):
    resp = await client.post("/trips", json={
        "destination": "A" * 201,
        "start_date": "2025-06-01",
        "end_date": "2025-06-03",
    }, headers=_OWNER_A)
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_create_trip_rejects_too_many_days(client):
    resp = await client.post("/trips", json={
        "destination": "Paris",
        "start_date": "2025-06-01",
        "end_date": "2025-08-01",  # 61 days — over limit
    }, headers=_OWNER_A)
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_create_trip_rejects_end_before_start(client):
    resp = await client.post("/trips", json={
        "destination": "Paris",
        "start_date": "2025-06-05",
        "end_date": "2025-06-01",
    }, headers=_OWNER_A)
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_create_trip_rejects_too_many_interests(client):
    resp = await client.post("/trips", json={
        "destination": "Paris",
        "start_date": "2025-06-01",
        "end_date": "2025-06-03",
        "interests": [f"interest{i}" for i in range(21)],  # 21 > max 20
    }, headers=_OWNER_A)
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_create_trip_rejects_tag_too_long(client):
    resp = await client.post("/trips", json={
        "destination": "Paris",
        "start_date": "2025-06-01",
        "end_date": "2025-06-03",
        "interests": ["x" * 61],  # 61 > max 60
    }, headers=_OWNER_A)
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_replan_rejects_empty_change_request(client):
    trip_id = await _create_trip(client)
    resp = await client.post(f"/trips/{trip_id}/replan", json={
        "change_request": "",
    }, headers=_OWNER_A)
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_replan_rejects_change_request_too_long(client):
    trip_id = await _create_trip(client)
    resp = await client.post(f"/trips/{trip_id}/replan", json={
        "change_request": "x" * 2001,
    }, headers=_OWNER_A)
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_health_still_works(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
