from datetime import date, time
from decimal import Decimal

import pytest

from app.models import (
    Activity,
    Pace,
    Trip,
    TripConstraints,
    TripDay,
    TripPreferences,
    WalkingTolerance,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_activity(**overrides) -> Activity:
    defaults = dict(
        name="Visit Museum",
        location="City Museum, Paris",
        start_time=time(9, 0),
        end_time=time(11, 0),
        estimated_cost=Decimal("15.00"),
        category="culture",
    )
    defaults.update(overrides)
    return Activity(**defaults)


def make_trip(**overrides) -> Trip:
    defaults = dict(
        destination="Paris",
        start_date=date(2025, 6, 1),
        end_date=date(2025, 6, 7),
    )
    defaults.update(overrides)
    return Trip(**defaults)


# ---------------------------------------------------------------------------
# Activity
# ---------------------------------------------------------------------------


class TestActivity:
    def test_valid_construction(self):
        a = make_activity()
        assert a.name == "Visit Museum"
        assert a.locked is False
        assert a.notes is None
        assert a.estimated_cost == Decimal("15.00")

    def test_end_time_before_start_raises(self):
        with pytest.raises(ValueError, match="end_time must be after start_time"):
            make_activity(start_time=time(11, 0), end_time=time(9, 0))

    def test_end_time_equal_to_start_raises(self):
        with pytest.raises(ValueError, match="end_time must be after start_time"):
            make_activity(start_time=time(9, 0), end_time=time(9, 0))

    def test_negative_cost_raises(self):
        with pytest.raises(ValueError):
            make_activity(estimated_cost=Decimal("-1.00"))

    def test_zero_cost_allowed(self):
        a = make_activity(estimated_cost=Decimal("0"))
        assert a.estimated_cost == Decimal("0")

    def test_locked_true(self):
        a = make_activity(locked=True)
        assert a.locked is True

    def test_locked_false(self):
        a = make_activity(locked=False)
        assert a.locked is False

    def test_notes_stored(self):
        a = make_activity(notes="Book in advance")
        assert a.notes == "Book in advance"

    def test_json_serialization_cost_is_float(self):
        a = make_activity(estimated_cost=Decimal("25.50"))
        data = a.model_dump(mode="json")
        assert isinstance(data["estimated_cost"], float)
        assert data["estimated_cost"] == 25.5

    def test_json_serialization_times_are_strings(self):
        a = make_activity(start_time=time(9, 0), end_time=time(11, 30))
        data = a.model_dump(mode="json")
        assert data["start_time"] == "09:00:00"
        assert data["end_time"] == "11:30:00"

    def test_roundtrip_serialization(self):
        original = make_activity()
        data = original.model_dump(mode="json")
        restored = Activity(**data)
        assert restored.name == original.name
        assert restored.start_time == original.start_time
        assert restored.end_time == original.end_time
        assert restored.estimated_cost == original.estimated_cost


# ---------------------------------------------------------------------------
# TripPreferences
# ---------------------------------------------------------------------------


class TestTripPreferences:
    def test_defaults(self):
        p = TripPreferences()
        assert p.interests == []
        assert p.food_preferences == []
        assert p.pace == Pace.MODERATE
        assert p.morning_preference is True
        assert p.walking_tolerance == WalkingTolerance.MODERATE

    def test_pace_relaxed(self):
        p = TripPreferences(pace="relaxed")
        assert p.pace == Pace.RELAXED

    def test_pace_busy(self):
        p = TripPreferences(pace="busy")
        assert p.pace == Pace.BUSY

    def test_invalid_pace_raises(self):
        with pytest.raises(ValueError):
            TripPreferences(pace="sprinting")

    def test_walking_tolerance_low(self):
        p = TripPreferences(walking_tolerance="low")
        assert p.walking_tolerance == WalkingTolerance.LOW

    def test_walking_tolerance_high(self):
        p = TripPreferences(walking_tolerance="high")
        assert p.walking_tolerance == WalkingTolerance.HIGH

    def test_invalid_walking_tolerance_raises(self):
        with pytest.raises(ValueError):
            TripPreferences(walking_tolerance="extreme")

    def test_morning_preference_false(self):
        p = TripPreferences(morning_preference=False)
        assert p.morning_preference is False

    def test_full_construction(self):
        p = TripPreferences(
            interests=["museums", "art"],
            food_preferences=["vegetarian", "local cuisine"],
            pace=Pace.RELAXED,
            morning_preference=False,
            walking_tolerance=WalkingTolerance.HIGH,
        )
        assert p.interests == ["museums", "art"]
        assert p.food_preferences == ["vegetarian", "local cuisine"]
        assert p.pace == Pace.RELAXED

    def test_pace_serializes_as_string(self):
        p = TripPreferences(pace=Pace.BUSY)
        data = p.model_dump(mode="json")
        assert data["pace"] == "busy"
        assert data["walking_tolerance"] == "moderate"


# ---------------------------------------------------------------------------
# TripConstraints
# ---------------------------------------------------------------------------


class TestTripConstraints:
    def test_all_none_by_default(self):
        c = TripConstraints()
        assert c.earliest_start_time is None
        assert c.latest_end_time is None
        assert c.maximum_budget is None

    def test_with_all_values(self):
        c = TripConstraints(
            earliest_start_time=time(8, 0),
            latest_end_time=time(22, 0),
            maximum_budget=Decimal("1000.00"),
        )
        assert c.earliest_start_time == time(8, 0)
        assert c.latest_end_time == time(22, 0)
        assert c.maximum_budget == Decimal("1000.00")

    def test_negative_budget_raises(self):
        with pytest.raises(ValueError):
            TripConstraints(maximum_budget=Decimal("-50.00"))

    def test_zero_budget_allowed(self):
        c = TripConstraints(maximum_budget=Decimal("0"))
        assert c.maximum_budget == Decimal("0")

    def test_budget_serializes_as_float(self):
        c = TripConstraints(maximum_budget=Decimal("500.00"))
        data = c.model_dump(mode="json")
        assert isinstance(data["maximum_budget"], float)
        assert data["maximum_budget"] == 500.0


# ---------------------------------------------------------------------------
# TripDay
# ---------------------------------------------------------------------------


class TestTripDay:
    def test_empty_activities_by_default(self):
        day = TripDay(date=date(2025, 6, 1))
        assert day.activities == []

    def test_with_activities(self):
        day = TripDay(date=date(2025, 6, 1), activities=[make_activity()])
        assert len(day.activities) == 1

    def test_date_stored_correctly(self):
        d = date(2025, 6, 15)
        day = TripDay(date=d)
        assert day.date == d


# ---------------------------------------------------------------------------
# Trip — date range validation
# ---------------------------------------------------------------------------


class TestTripDateValidation:
    def test_valid_date_range(self):
        trip = make_trip(start_date=date(2025, 6, 1), end_date=date(2025, 6, 7))
        assert trip.start_date < trip.end_date

    def test_same_start_and_end_date(self):
        trip = make_trip(start_date=date(2025, 6, 1), end_date=date(2025, 6, 1))
        assert trip.start_date == trip.end_date

    def test_end_before_start_raises(self):
        with pytest.raises(ValueError, match="end_date cannot be before start_date"):
            make_trip(start_date=date(2025, 6, 7), end_date=date(2025, 6, 1))

    def test_negative_budget_raises(self):
        with pytest.raises(ValueError):
            make_trip(total_budget=Decimal("-100.00"))

    def test_zero_budget_allowed(self):
        trip = make_trip(total_budget=Decimal("0"))
        assert trip.total_budget == Decimal("0")

    def test_budget_serializes_as_float(self):
        trip = make_trip(total_budget=Decimal("2500.00"))
        data = trip.model_dump(mode="json")
        assert isinstance(data["total_budget"], float)
        assert data["total_budget"] == 2500.0


# ---------------------------------------------------------------------------
# Trip — TripDay range and duplicate validation
# ---------------------------------------------------------------------------


class TestTripDayValidation:
    def test_day_on_start_date_allowed(self):
        trip = make_trip(
            start_date=date(2025, 6, 1),
            end_date=date(2025, 6, 3),
            days=[TripDay(date=date(2025, 6, 1))],
        )
        assert len(trip.days) == 1

    def test_day_on_end_date_allowed(self):
        trip = make_trip(
            start_date=date(2025, 6, 1),
            end_date=date(2025, 6, 3),
            days=[TripDay(date=date(2025, 6, 3))],
        )
        assert len(trip.days) == 1

    def test_multiple_days_within_range(self):
        trip = make_trip(
            start_date=date(2025, 6, 1),
            end_date=date(2025, 6, 3),
            days=[
                TripDay(date=date(2025, 6, 1)),
                TripDay(date=date(2025, 6, 2)),
                TripDay(date=date(2025, 6, 3)),
            ],
        )
        assert len(trip.days) == 3

    def test_day_before_start_raises(self):
        with pytest.raises(ValueError, match="outside the trip range"):
            make_trip(
                start_date=date(2025, 6, 1),
                end_date=date(2025, 6, 3),
                days=[TripDay(date=date(2025, 5, 31))],
            )

    def test_day_after_end_raises(self):
        with pytest.raises(ValueError, match="outside the trip range"):
            make_trip(
                start_date=date(2025, 6, 1),
                end_date=date(2025, 6, 3),
                days=[TripDay(date=date(2025, 6, 4))],
            )

    def test_duplicate_day_dates_raise(self):
        with pytest.raises(ValueError, match="Duplicate TripDay date"):
            make_trip(
                start_date=date(2025, 6, 1),
                end_date=date(2025, 6, 3),
                days=[
                    TripDay(date=date(2025, 6, 1)),
                    TripDay(date=date(2025, 6, 1)),
                ],
            )


# ---------------------------------------------------------------------------
# Trip — full serialization
# ---------------------------------------------------------------------------


class TestTripSerialization:
    def test_json_dates_are_strings(self):
        trip = make_trip()
        data = trip.model_dump(mode="json")
        assert data["start_date"] == "2025-06-01"
        assert data["end_date"] == "2025-06-07"

    def test_nested_preferences_serialized(self):
        trip = make_trip(preferences=TripPreferences(pace=Pace.RELAXED))
        data = trip.model_dump(mode="json")
        assert data["preferences"]["pace"] == "relaxed"

    def test_nested_activity_cost_is_float(self):
        activity = make_activity(estimated_cost=Decimal("30.00"))
        trip = Trip(
            destination="Paris",
            start_date=date(2025, 6, 1),
            end_date=date(2025, 6, 3),
            days=[TripDay(date=date(2025, 6, 1), activities=[activity])],
        )
        data = trip.model_dump(mode="json")
        cost = data["days"][0]["activities"][0]["estimated_cost"]
        assert isinstance(cost, float)
        assert cost == 30.0

    def test_full_roundtrip(self):
        original = Trip(
            destination="Tokyo",
            start_date=date(2025, 9, 1),
            end_date=date(2025, 9, 5),
            total_budget=Decimal("3000.00"),
            preferences=TripPreferences(
                interests=["temples", "food"],
                pace=Pace.MODERATE,
                walking_tolerance=WalkingTolerance.HIGH,
            ),
            constraints=TripConstraints(earliest_start_time=time(8, 0)),
            days=[
                TripDay(
                    date=date(2025, 9, 1),
                    activities=[make_activity(name="Senso-ji Temple")],
                )
            ],
        )
        data = original.model_dump(mode="json")
        restored = Trip(**data)
        assert restored.destination == original.destination
        assert restored.start_date == original.start_date
        assert restored.preferences.pace == original.preferences.pace
        assert restored.days[0].activities[0].name == "Senso-ji Temple"
