"""Tests for the deterministic itinerary validator."""
import pytest
from datetime import date, time
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from app.models.trip import Activity, Trip, TripConstraints, TripDay, TripPreferences
from app.tools.models import GeocodingLocation, Route, TravelMode
from app.validation.itinerary import (
    TRANSITION_BUFFER_SECONDS,
    ValidationResult,
    validate_itinerary,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_trip(
    *,
    days: list[TripDay] | None = None,
    total_budget: Decimal | None = None,
    maximum_budget: Decimal | None = None,
) -> Trip:
    constraints = TripConstraints(maximum_budget=maximum_budget)
    return Trip(
        destination="Paris",
        start_date=date(2025, 6, 1),
        end_date=date(2025, 6, 3),
        total_budget=total_budget,
        constraints=constraints,
        days=days or [],
    )


def make_activity(
    name: str,
    start: str,
    end: str,
    *,
    locked: bool = False,
    cost: float = 0.0,
    location: str = "Paris, France",
) -> Activity:
    return Activity(
        name=name,
        location=location,
        start_time=time.fromisoformat(start),
        end_time=time.fromisoformat(end),
        estimated_cost=Decimal(str(cost)),
        category="sightseeing",
        locked=locked,
    )


def make_day(d: str, activities: list[Activity]) -> TripDay:
    return TripDay(date=date.fromisoformat(d), activities=activities)


# ---------------------------------------------------------------------------
# Rule A: schedule overlap
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_no_overlap_is_valid():
    day = make_day("2025-06-01", [
        make_activity("Museum", "09:00:00", "11:00:00"),
        make_activity("Lunch", "12:00:00", "13:00:00"),
    ])
    result = await validate_itinerary(make_trip(days=[day]))
    assert result.valid
    assert not result.errors


@pytest.mark.anyio
async def test_exact_boundary_is_valid():
    """end_time of one == start_time of next: no overlap."""
    day = make_day("2025-06-01", [
        make_activity("Museum", "09:00:00", "11:00:00"),
        make_activity("Lunch", "11:00:00", "12:00:00"),
    ])
    result = await validate_itinerary(make_trip(days=[day]))
    assert result.valid


@pytest.mark.anyio
async def test_overlap_produces_error():
    day = make_day("2025-06-01", [
        make_activity("Museum", "09:00:00", "12:00:00"),
        make_activity("Lunch", "11:00:00", "13:00:00"),
    ])
    result = await validate_itinerary(make_trip(days=[day]))
    assert not result.valid
    assert any(i.rule == "schedule.overlap" for i in result.errors)


@pytest.mark.anyio
async def test_overlap_message_contains_activity_names():
    day = make_day("2025-06-01", [
        make_activity("Alpha", "09:00:00", "12:00:00"),
        make_activity("Beta", "10:00:00", "13:00:00"),
    ])
    result = await validate_itinerary(make_trip(days=[day]))
    msg = result.errors[0].message
    assert "Alpha" in msg
    assert "Beta" in msg


@pytest.mark.anyio
async def test_overlap_checks_sorted_order():
    """Activities provided out of time-order should still detect the overlap."""
    day = make_day("2025-06-01", [
        make_activity("Late", "10:00:00", "12:00:00"),
        make_activity("Early", "09:00:00", "11:00:00"),  # overlaps with Late
    ])
    result = await validate_itinerary(make_trip(days=[day]))
    assert not result.valid
    assert any(i.rule == "schedule.overlap" for i in result.errors)


@pytest.mark.anyio
async def test_overlap_on_multiple_days_each_reported():
    day1 = make_day("2025-06-01", [
        make_activity("A", "09:00:00", "11:00:00"),
        make_activity("B", "10:00:00", "12:00:00"),
    ])
    day2 = make_day("2025-06-02", [
        make_activity("C", "14:00:00", "16:00:00"),
        make_activity("D", "15:00:00", "17:00:00"),
    ])
    result = await validate_itinerary(make_trip(days=[day1, day2]))
    overlap_errors = [i for i in result.issues if i.rule == "schedule.overlap"]
    assert len(overlap_errors) == 2


# ---------------------------------------------------------------------------
# Rule B: locked-activity preservation
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_locked_activity_preserved():
    locked_act = make_activity("Eiffel Tower", "10:00:00", "12:00:00", locked=True)
    original = make_trip(days=[make_day("2025-06-01", [locked_act])])
    updated = make_trip(days=[make_day("2025-06-01", [locked_act])])
    result = await validate_itinerary(updated, original_trip=original)
    assert result.valid


@pytest.mark.anyio
async def test_locked_activity_removed_is_error():
    locked_act = make_activity("Eiffel Tower", "10:00:00", "12:00:00", locked=True)
    original = make_trip(days=[make_day("2025-06-01", [locked_act])])
    updated = make_trip(days=[make_day("2025-06-01", [])])
    result = await validate_itinerary(updated, original_trip=original)
    assert not result.valid
    assert any(i.rule == "locked.removed" for i in result.errors)


@pytest.mark.anyio
async def test_locked_activity_time_changed_is_error():
    original_act = make_activity("Eiffel Tower", "10:00:00", "12:00:00", locked=True)
    modified_act = make_activity("Eiffel Tower", "11:00:00", "13:00:00", locked=True)
    original = make_trip(days=[make_day("2025-06-01", [original_act])])
    updated = make_trip(days=[make_day("2025-06-01", [modified_act])])
    result = await validate_itinerary(updated, original_trip=original)
    assert not result.valid
    assert any(i.rule == "locked.modified" for i in result.errors)


@pytest.mark.anyio
async def test_locked_activity_date_changed_is_error():
    original_act = make_activity("Eiffel Tower", "10:00:00", "12:00:00", locked=True)
    updated_act = make_activity("Eiffel Tower", "10:00:00", "12:00:00", locked=True)
    original = make_trip(days=[
        make_day("2025-06-01", [original_act]),
        make_day("2025-06-02", []),
    ])
    updated = make_trip(days=[
        make_day("2025-06-01", []),
        make_day("2025-06-02", [updated_act]),
    ])
    result = await validate_itinerary(updated, original_trip=original)
    assert not result.valid
    assert any(i.rule == "locked.modified" for i in result.errors)


@pytest.mark.anyio
async def test_unlocked_activity_can_be_freely_changed():
    original_act = make_activity("Free Lunch", "12:00:00", "13:00:00", locked=False)
    updated_act = make_activity("Free Lunch", "13:00:00", "14:00:00", locked=False)
    original = make_trip(days=[make_day("2025-06-01", [original_act])])
    updated = make_trip(days=[make_day("2025-06-01", [updated_act])])
    result = await validate_itinerary(updated, original_trip=original)
    assert result.valid


@pytest.mark.anyio
async def test_no_original_trip_skips_locked_check():
    """When original_trip is None, locked-check is not performed."""
    locked_act = make_activity("Eiffel Tower", "10:00:00", "12:00:00", locked=True)
    trip = make_trip(days=[make_day("2025-06-01", [locked_act])])
    result = await validate_itinerary(trip, original_trip=None)
    assert result.valid


# ---------------------------------------------------------------------------
# Rule C: budget
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_budget_within_limit_is_valid():
    day = make_day("2025-06-01", [
        make_activity("Museum", "09:00:00", "11:00:00", cost=20.0),
        make_activity("Lunch", "12:00:00", "13:00:00", cost=15.0),
    ])
    result = await validate_itinerary(make_trip(days=[day], total_budget=Decimal("100")))
    assert result.valid


@pytest.mark.anyio
async def test_budget_exactly_at_limit_is_valid():
    day = make_day("2025-06-01", [
        make_activity("Museum", "09:00:00", "11:00:00", cost=50.0),
        make_activity("Dinner", "19:00:00", "20:00:00", cost=50.0),
    ])
    result = await validate_itinerary(make_trip(days=[day], total_budget=Decimal("100")))
    assert result.valid


@pytest.mark.anyio
async def test_budget_exceeded_is_error():
    day = make_day("2025-06-01", [
        make_activity("Expensive Tour", "09:00:00", "11:00:00", cost=200.0),
    ])
    result = await validate_itinerary(make_trip(days=[day], total_budget=Decimal("100")))
    assert not result.valid
    assert any(i.rule == "budget.exceeded" for i in result.errors)


@pytest.mark.anyio
async def test_maximum_budget_constraint_used_when_tighter():
    day = make_day("2025-06-01", [
        make_activity("Tour", "09:00:00", "11:00:00", cost=120.0),
    ])
    # total_budget=200 but constraints.maximum_budget=100 — tighter wins
    trip = Trip(
        destination="Paris",
        start_date=date(2025, 6, 1),
        end_date=date(2025, 6, 3),
        total_budget=Decimal("200"),
        constraints=TripConstraints(maximum_budget=Decimal("100")),
        days=[day],
    )
    result = await validate_itinerary(trip)
    assert not result.valid
    assert any(i.rule == "budget.exceeded" for i in result.errors)


@pytest.mark.anyio
async def test_no_budget_set_skips_budget_check():
    day = make_day("2025-06-01", [
        make_activity("Tour", "09:00:00", "11:00:00", cost=99999.0),
    ])
    result = await validate_itinerary(make_trip(days=[day]))
    assert result.valid


@pytest.mark.anyio
async def test_budget_error_message_contains_amounts():
    day = make_day("2025-06-01", [
        make_activity("Tour", "09:00:00", "11:00:00", cost=150.0),
    ])
    result = await validate_itinerary(make_trip(days=[day], total_budget=Decimal("100")))
    msg = result.errors[0].message
    assert "150" in msg
    assert "100" in msg


# ---------------------------------------------------------------------------
# Rule D (fast): travel gap heuristic
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_sufficient_gap_no_warning():
    day = make_day("2025-06-01", [
        make_activity("Museum", "09:00:00", "11:00:00"),
        make_activity("Lunch", "11:30:00", "12:30:00"),  # 30-min gap
    ])
    result = await validate_itinerary(make_trip(days=[day]))
    assert result.valid
    assert not result.warnings


@pytest.mark.anyio
async def test_tight_gap_produces_warning():
    day = make_day("2025-06-01", [
        make_activity("Museum", "09:00:00", "11:00:00"),
        make_activity("Lunch", "11:05:00", "12:00:00"),  # 5-min gap
    ])
    result = await validate_itinerary(make_trip(days=[day]))
    assert result.valid  # warning, not error
    assert any(i.rule == "travel.tight_gap" for i in result.warnings)


@pytest.mark.anyio
async def test_exactly_10_min_gap_no_warning():
    day = make_day("2025-06-01", [
        make_activity("Museum", "09:00:00", "11:00:00"),
        make_activity("Lunch", "11:10:00", "12:00:00"),  # exactly 10 min
    ])
    result = await validate_itinerary(make_trip(days=[day]))
    assert not result.warnings


@pytest.mark.anyio
async def test_zero_gap_no_warning_because_handled_by_overlap():
    """A zero gap means exact boundary — not a tight gap, not an overlap."""
    day = make_day("2025-06-01", [
        make_activity("Museum", "09:00:00", "11:00:00"),
        make_activity("Lunch", "11:00:00", "12:00:00"),
    ])
    result = await validate_itinerary(make_trip(days=[day]))
    assert not result.warnings
    assert not result.errors


# ---------------------------------------------------------------------------
# Rule D (full): routing-based feasibility
# ---------------------------------------------------------------------------


def _make_geocode_side_effect(lat: float, lng: float):
    return GeocodingLocation(
        name="Paris",
        latitude=lat,
        longitude=lng,
        country="France",
        admin1="Île-de-France",
    )


@pytest.mark.anyio
async def test_routing_feasible_no_error():
    day = make_day("2025-06-01", [
        make_activity("Museum", "09:00:00", "11:00:00", location="Louvre, Paris"),
        make_activity("Lunch", "12:00:00", "13:00:00", location="Café de Flore, Paris"),
    ])
    trip = make_trip(days=[day])

    mock_route = Route(
        origin_lat=48.861, origin_lng=2.337,
        destination_lat=48.854, destination_lng=2.332,
        distance_meters=1000,
        duration_seconds=600,  # 10 min walk — fits in the 60-min gap after buffer
        travel_mode=TravelMode.WALK,
    )

    with (
        patch(
            "app.validation.itinerary.geocode_location",
            side_effect=[
                _make_geocode_side_effect(48.861, 2.337),
                _make_geocode_side_effect(48.854, 2.332),
            ],
        ),
        patch(
            "app.validation.itinerary.get_route",
            return_value=mock_route,
        ),
    ):
        result = await validate_itinerary(trip, check_routing=True)

    assert result.valid
    assert not result.errors


@pytest.mark.anyio
async def test_routing_infeasible_produces_error():
    day = make_day("2025-06-01", [
        make_activity("Museum", "09:00:00", "11:00:00", location="Louvre, Paris"),
        make_activity("Lunch", "11:05:00", "12:00:00", location="Versailles, France"),
    ])
    trip = make_trip(days=[day])

    mock_route = Route(
        origin_lat=48.861, origin_lng=2.337,
        destination_lat=48.804, destination_lng=2.120,
        distance_meters=20000,
        duration_seconds=3600,  # 60-min walk — far more than the 5-min gap
        travel_mode=TravelMode.WALK,
    )

    with (
        patch(
            "app.validation.itinerary.geocode_location",
            side_effect=[
                _make_geocode_side_effect(48.861, 2.337),
                _make_geocode_side_effect(48.804, 2.120),
            ],
        ),
        patch(
            "app.validation.itinerary.get_route",
            return_value=mock_route,
        ),
    ):
        result = await validate_itinerary(trip, check_routing=True)

    assert not result.valid
    assert any(i.rule == "travel.infeasible" for i in result.errors)


@pytest.mark.anyio
async def test_routing_geocode_failure_skips_pair():
    """GeocodingError for a pair → silently skip, no error reported."""
    from app.tools.exceptions import GeocodingError

    day = make_day("2025-06-01", [
        make_activity("Museum", "09:00:00", "11:00:00"),
        make_activity("Lunch", "11:05:00", "12:00:00"),
    ])
    trip = make_trip(days=[day])

    with patch(
        "app.validation.itinerary.geocode_location",
        side_effect=GeocodingError("Not found"),
    ):
        result = await validate_itinerary(trip, check_routing=True)

    assert result.valid


@pytest.mark.anyio
async def test_routing_route_failure_skips_pair():
    """RoutingError → silently skip."""
    from app.tools.exceptions import RoutingError

    day = make_day("2025-06-01", [
        make_activity("Museum", "09:00:00", "11:00:00", location="Louvre, Paris"),
        make_activity("Lunch", "11:05:00", "12:00:00", location="Versailles, France"),
    ])
    trip = make_trip(days=[day])

    with (
        patch(
            "app.validation.itinerary.geocode_location",
            side_effect=[
                _make_geocode_side_effect(48.861, 2.337),
                _make_geocode_side_effect(48.804, 2.120),
            ],
        ),
        patch(
            "app.validation.itinerary.get_route",
            side_effect=RoutingError("Service unavailable"),
        ),
    ):
        result = await validate_itinerary(trip, check_routing=True)

    assert result.valid


@pytest.mark.anyio
async def test_routing_overlap_pair_skipped():
    """Pairs with gap <= 0 are skipped (overlap already flagged by schedule check)."""
    day = make_day("2025-06-01", [
        make_activity("Museum", "09:00:00", "12:00:00"),
        make_activity("Lunch", "11:00:00", "13:00:00"),
    ])
    trip = make_trip(days=[day])

    with patch("app.validation.itinerary.geocode_location") as mock_geo:
        result = await validate_itinerary(trip, check_routing=True)

    # geocode should never have been called — the overlap pair was skipped
    mock_geo.assert_not_called()
    assert any(i.rule == "schedule.overlap" for i in result.errors)


@pytest.mark.anyio
async def test_routing_infeasible_message_contains_details():
    day = make_day("2025-06-01", [
        make_activity("A", "09:00:00", "11:00:00", location="X"),
        make_activity("B", "11:05:00", "12:00:00", location="Y"),
    ])
    trip = make_trip(days=[day])

    mock_route = Route(
        origin_lat=48.861, origin_lng=2.337,
        destination_lat=48.804, destination_lng=2.120,
        distance_meters=5000,
        duration_seconds=1800,
        travel_mode=TravelMode.WALK,
    )

    with (
        patch(
            "app.validation.itinerary.geocode_location",
            side_effect=[
                _make_geocode_side_effect(48.861, 2.337),
                _make_geocode_side_effect(48.804, 2.120),
            ],
        ),
        patch(
            "app.validation.itinerary.get_route",
            return_value=mock_route,
        ),
    ):
        result = await validate_itinerary(trip, check_routing=True)

    err = next(i for i in result.errors if i.rule == "travel.infeasible")
    assert "A" in err.message
    assert "B" in err.message


# ---------------------------------------------------------------------------
# ValidationResult properties
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_result_errors_and_warnings_split():
    """Verify .errors and .warnings filter correctly."""
    day = make_day("2025-06-01", [
        make_activity("A", "09:00:00", "12:00:00"),
        make_activity("B", "10:00:00", "13:00:00"),  # overlap — error
        make_activity("C", "13:02:00", "14:00:00"),  # 2-min gap — warning
    ])
    result = await validate_itinerary(make_trip(days=[day]))
    assert not result.valid
    assert len(result.errors) >= 1
    assert all(i.severity == "error" for i in result.errors)
    assert all(i.severity == "warning" for i in result.warnings)


@pytest.mark.anyio
async def test_empty_trip_is_valid():
    result = await validate_itinerary(make_trip())
    assert result.valid
    assert result.issues == []
