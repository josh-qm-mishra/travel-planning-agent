"""Tests for TripRepository — all operations against an in-memory SQLite DB."""
import asyncio
import json
from datetime import date

import pytest

from app.db.repository import ConflictError, TripRepository
from app.models.trip import Trip


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_trip(
    destination: str = "Paris",
    start: str = "2025-06-01",
    end: str = "2025-06-03",
) -> Trip:
    return Trip(
        destination=destination,
        start_date=date.fromisoformat(start),
        end_date=date.fromisoformat(end),
    )


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_create_assigns_id(db_session):
    record = await TripRepository(db_session).create(make_trip())
    assert record.id
    assert len(record.id) == 36  # UUID with hyphens


@pytest.mark.anyio
async def test_create_stores_metadata(db_session):
    record = await TripRepository(db_session).create(make_trip("Tokyo", "2025-07-01", "2025-07-05"))
    assert record.destination == "Tokyo"
    assert record.start_date == date(2025, 7, 1)
    assert record.end_date == date(2025, 7, 5)


@pytest.mark.anyio
async def test_create_stores_trip_json(db_session):
    trip = make_trip("Paris")
    record = await TripRepository(db_session).create(trip)
    restored = Trip(**json.loads(record.trip_data))
    assert restored.destination == "Paris"
    assert restored.start_date == trip.start_date


@pytest.mark.anyio
async def test_create_sets_timestamps(db_session):
    record = await TripRepository(db_session).create(make_trip())
    assert record.created_at is not None
    assert record.updated_at is not None


@pytest.mark.anyio
async def test_create_ids_are_unique(db_session):
    repo = TripRepository(db_session)
    r1 = await repo.create(make_trip())
    r2 = await repo.create(make_trip())
    assert r1.id != r2.id


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_get_returns_matching_record(db_session):
    repo = TripRepository(db_session)
    created = await repo.create(make_trip())
    fetched = await repo.get(created.id)
    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.destination == created.destination


@pytest.mark.anyio
async def test_get_nonexistent_returns_none(db_session):
    result = await TripRepository(db_session).get("00000000-0000-0000-0000-000000000000")
    assert result is None


@pytest.mark.anyio
async def test_get_wrong_id_returns_none(db_session):
    repo = TripRepository(db_session)
    await repo.create(make_trip())
    result = await repo.get("this-does-not-exist")
    assert result is None


# ---------------------------------------------------------------------------
# list_all
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_list_empty_database(db_session):
    records = await TripRepository(db_session).list_all()
    assert records == []


@pytest.mark.anyio
async def test_list_returns_all_trips(db_session):
    repo = TripRepository(db_session)
    await repo.create(make_trip("Paris"))
    await repo.create(make_trip("Tokyo"))
    await repo.create(make_trip("Rome"))
    records = await repo.list_all()
    assert len(records) == 3
    destinations = {r.destination for r in records}
    assert destinations == {"Paris", "Tokyo", "Rome"}


@pytest.mark.anyio
async def test_list_ordered_newest_first(db_session):
    repo = TripRepository(db_session)
    first = await repo.create(make_trip("Paris"))
    # Small pause so timestamps differ
    await asyncio.sleep(0.05)
    second = await repo.create(make_trip("Tokyo"))

    records = await repo.list_all()
    assert records[0].id == second.id
    assert records[1].id == first.id


# ---------------------------------------------------------------------------
# update
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_update_changes_destination(db_session):
    repo = TripRepository(db_session)
    record = await repo.create(make_trip("Paris"))
    updated = await repo.update(record.id, make_trip("Tokyo", "2025-07-01", "2025-07-05"))
    assert updated.destination == "Tokyo"
    assert updated.start_date == date(2025, 7, 1)


@pytest.mark.anyio
async def test_update_preserves_id(db_session):
    repo = TripRepository(db_session)
    record = await repo.create(make_trip())
    original_id = record.id
    updated = await repo.update(record.id, make_trip("Tokyo", "2025-07-01", "2025-07-05"))
    assert updated.id == original_id


@pytest.mark.anyio
async def test_update_stores_new_trip_json(db_session):
    repo = TripRepository(db_session)
    record = await repo.create(make_trip("Paris"))
    await repo.update(record.id, make_trip("Tokyo", "2025-07-01", "2025-07-05"))
    refetched = await repo.get(record.id)
    restored = Trip(**json.loads(refetched.trip_data))
    assert restored.destination == "Tokyo"


@pytest.mark.anyio
async def test_update_advances_updated_at(db_session):
    repo = TripRepository(db_session)
    record = await repo.create(make_trip())
    original_ts = record.updated_at
    await asyncio.sleep(0.05)
    updated = await repo.update(record.id, make_trip("Tokyo", "2025-07-01", "2025-07-05"))
    assert updated.updated_at >= original_ts


@pytest.mark.anyio
async def test_update_nonexistent_raises_value_error(db_session):
    with pytest.raises(ValueError, match="not found"):
        await TripRepository(db_session).update("nonexistent", make_trip())


@pytest.mark.anyio
async def test_update_does_not_change_created_at(db_session):
    repo = TripRepository(db_session)
    record = await repo.create(make_trip())
    original_created = record.created_at
    await asyncio.sleep(0.05)
    updated = await repo.update(record.id, make_trip("Tokyo", "2025-07-01", "2025-07-05"))
    assert updated.created_at == original_created


# ---------------------------------------------------------------------------
# version / optimistic concurrency
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_create_sets_version_to_one(db_session):
    record = await TripRepository(db_session).create(make_trip())
    assert record.version == 1


@pytest.mark.anyio
async def test_unconditional_update_increments_version(db_session):
    repo = TripRepository(db_session)
    record = await repo.create(make_trip())
    assert record.version == 1
    updated = await repo.update(record.id, make_trip("Tokyo", "2025-07-01", "2025-07-05"))
    assert updated.version == 2


@pytest.mark.anyio
async def test_conditional_update_succeeds_with_correct_version(db_session):
    repo = TripRepository(db_session)
    record = await repo.create(make_trip())
    updated = await repo.update(record.id, make_trip("Tokyo", "2025-07-01", "2025-07-05"), expected_version=1)
    assert updated.version == 2
    assert updated.destination == "Tokyo"


@pytest.mark.anyio
async def test_conditional_update_increments_version(db_session):
    repo = TripRepository(db_session)
    record = await repo.create(make_trip())
    u1 = await repo.update(record.id, make_trip("Tokyo", "2025-07-01", "2025-07-05"), expected_version=1)
    assert u1.version == 2
    u2 = await repo.update(record.id, make_trip("Rome", "2025-08-01", "2025-08-03"), expected_version=2)
    assert u2.version == 3


@pytest.mark.anyio
async def test_conditional_update_stale_version_raises_conflict(db_session):
    repo = TripRepository(db_session)
    record = await repo.create(make_trip())
    # Advance the version to 2.
    await repo.update(record.id, make_trip("Tokyo", "2025-07-01", "2025-07-05"), expected_version=1)

    # A second writer still holds the old version=1.
    with pytest.raises(ConflictError):
        await repo.update(record.id, make_trip("Berlin", "2025-08-01", "2025-08-03"), expected_version=1)


@pytest.mark.anyio
async def test_conditional_update_lost_update_prevention(db_session):
    """Simulate two concurrent replans; only the first should succeed."""
    repo = TripRepository(db_session)
    record = await repo.create(make_trip("Paris"))
    original_version = record.version  # == 1

    # Writer A succeeds and increments version to 2.
    await repo.update(record.id, make_trip("Tokyo", "2025-07-01", "2025-07-05"), expected_version=original_version)

    # Writer B, which also read version 1, now tries to write.
    with pytest.raises(ConflictError):
        await repo.update(record.id, make_trip("Rome", "2025-08-01", "2025-08-03"), expected_version=original_version)

    # The winning write (Tokyo) must be preserved.
    final = await repo.get(record.id)
    assert final is not None
    assert final.destination == "Tokyo"
    assert final.version == 2


@pytest.mark.anyio
async def test_conditional_update_nonexistent_raises_value_error(db_session):
    with pytest.raises(ValueError, match="not found"):
        await TripRepository(db_session).update("nonexistent-id", make_trip(), expected_version=1)
