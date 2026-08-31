"""Fixture planning eval cases — no live agent calls."""
from __future__ import annotations

from datetime import date, time
from decimal import Decimal

from ...agent.models import TripPlanRequest
from ...models.trip import Activity, Pace, Trip, TripConstraints, TripDay, TripPreferences
from ..checks import (
    all_days_represented,
    budget_respected,
    dates_match,
    destination_preserved,
    has_activities,
    locked_activities_present,
    no_overlapping_activities,
)
from ..models import PlanningEvalCase

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _req(
    destination: str = "Paris",
    start: str = "2025-06-01",
    end: str = "2025-06-01",
    budget: str | None = None,
    locked: list | None = None,
    max_budget: str | None = None,
) -> TripPlanRequest:
    constraints = TripConstraints(
        maximum_budget=Decimal(max_budget) if max_budget else None
    )
    return TripPlanRequest(
        destination=destination,
        start_date=date.fromisoformat(start),
        end_date=date.fromisoformat(end),
        total_budget=Decimal(budget) if budget else None,
        locked_activities=locked or [],
        constraints=constraints,
    )


def _act(
    name: str,
    start: str,
    end: str,
    cost: str = "0",
    locked: bool = False,
    category: str = "sightseeing",
) -> Activity:
    return Activity(
        name=name,
        location="Somewhere",
        start_time=time.fromisoformat(start),
        end_time=time.fromisoformat(end),
        estimated_cost=Decimal(cost),
        category=category,
        locked=locked,
    )


def _trip(destination: str, start: str, end: str, days: list[TripDay]) -> Trip:
    return Trip(
        destination=destination,
        start_date=date.fromisoformat(start),
        end_date=date.fromisoformat(end),
        days=days,
    )


def _day(d: str, acts: list[Activity]) -> TripDay:
    return TripDay(date=date.fromisoformat(d), activities=acts)


# ---------------------------------------------------------------------------
# Positive cases (7): valid trips that should pass all checks
# ---------------------------------------------------------------------------

POSITIVE_CASES: list[PlanningEvalCase] = [
    PlanningEvalCase(
        id="plan_pos_01",
        name="correct 1-day trip",
        request=_req("Paris", "2025-06-01", "2025-06-01"),
        candidate_trip=_trip(
            "Paris",
            "2025-06-01",
            "2025-06-01",
            [_day("2025-06-01", [_act("Eiffel Tower", "09:00", "11:00")])],
        ),
        checks=[
            dates_match(_req("Paris", "2025-06-01", "2025-06-01")),
            destination_preserved(_req("Paris", "2025-06-01", "2025-06-01")),
            no_overlapping_activities(),
            has_activities(),
            all_days_represented(_req("Paris", "2025-06-01", "2025-06-01")),
        ],
    ),
    PlanningEvalCase(
        id="plan_pos_02",
        name="multi-day trip all days covered",
        request=_req("Tokyo", "2025-07-01", "2025-07-03"),
        candidate_trip=_trip(
            "Tokyo",
            "2025-07-01",
            "2025-07-03",
            [
                _day("2025-07-01", [_act("Senso-ji Temple", "09:00", "11:00")]),
                _day("2025-07-02", [_act("Shibuya Crossing", "10:00", "12:00")]),
                _day("2025-07-03", [_act("Tsukiji Market", "08:00", "10:00")]),
            ],
        ),
        checks=[
            dates_match(_req("Tokyo", "2025-07-01", "2025-07-03")),
            destination_preserved(_req("Tokyo", "2025-07-01", "2025-07-03")),
            no_overlapping_activities(),
            all_days_represented(_req("Tokyo", "2025-07-01", "2025-07-03")),
        ],
    ),
    PlanningEvalCase(
        id="plan_pos_03",
        name="trip under budget",
        request=_req("Rome", "2025-08-01", "2025-08-01", budget="200"),
        candidate_trip=_trip(
            "Rome",
            "2025-08-01",
            "2025-08-01",
            [
                _day(
                    "2025-08-01",
                    [
                        _act("Colosseum", "09:00", "11:00", cost="20"),
                        _act("Roman Forum", "11:30", "13:00", cost="10"),
                    ],
                )
            ],
        ),
        checks=[
            dates_match(_req("Rome", "2025-08-01", "2025-08-01")),
            budget_respected(Decimal("200")),
            no_overlapping_activities(),
        ],
    ),
    PlanningEvalCase(
        id="plan_pos_04",
        name="exact budget match",
        request=_req("Berlin", "2025-09-01", "2025-09-01", budget="50"),
        candidate_trip=_trip(
            "Berlin",
            "2025-09-01",
            "2025-09-01",
            [
                _day(
                    "2025-09-01",
                    [
                        _act("Brandenburg Gate", "09:00", "10:00", cost="0"),
                        _act("Museum Island", "10:30", "12:30", cost="50"),
                    ],
                )
            ],
        ),
        checks=[
            budget_respected(Decimal("50")),
            no_overlapping_activities(),
        ],
    ),
    PlanningEvalCase(
        id="plan_pos_05",
        name="locked activity preserved",
        request=_req(
            "Barcelona",
            "2025-10-01",
            "2025-10-01",
            locked=[_act("Sagrada Familia", "14:00", "16:00", locked=True)],
        ),
        candidate_trip=_trip(
            "Barcelona",
            "2025-10-01",
            "2025-10-01",
            [
                _day(
                    "2025-10-01",
                    [
                        _act("Park Guell", "09:00", "11:00"),
                        _act("Sagrada Familia", "14:00", "16:00", locked=True),
                    ],
                )
            ],
        ),
        checks=[
            locked_activities_present(
                [_act("Sagrada Familia", "14:00", "16:00", locked=True)]
            ),
            no_overlapping_activities(),
        ],
    ),
    PlanningEvalCase(
        id="plan_pos_06",
        name="multiple locked activities present",
        request=_req(
            "London",
            "2025-11-01",
            "2025-11-01",
            locked=[
                _act("British Museum", "09:00", "11:00", locked=True),
                _act("Tower of London", "13:00", "15:00", locked=True),
            ],
        ),
        candidate_trip=_trip(
            "London",
            "2025-11-01",
            "2025-11-01",
            [
                _day(
                    "2025-11-01",
                    [
                        _act("British Museum", "09:00", "11:00", locked=True),
                        _act("Tower of London", "13:00", "15:00", locked=True),
                    ],
                )
            ],
        ),
        checks=[
            locked_activities_present(
                [
                    _act("British Museum", "09:00", "11:00", locked=True),
                    _act("Tower of London", "13:00", "15:00", locked=True),
                ]
            ),
            no_overlapping_activities(),
        ],
    ),
    PlanningEvalCase(
        id="plan_pos_07",
        name="multi-day with budget respected",
        request=_req("Amsterdam", "2025-12-01", "2025-12-02", budget="100"),
        candidate_trip=_trip(
            "Amsterdam",
            "2025-12-01",
            "2025-12-02",
            [
                _day("2025-12-01", [_act("Rijksmuseum", "10:00", "12:00", cost="25")]),
                _day("2025-12-02", [_act("Anne Frank House", "10:00", "12:00", cost="15")]),
            ],
        ),
        checks=[
            all_days_represented(_req("Amsterdam", "2025-12-01", "2025-12-02")),
            budget_respected(Decimal("100")),
            no_overlapping_activities(),
        ],
    ),
]


# ---------------------------------------------------------------------------
# Negative cases (9): trips with violations that checks must detect
# ---------------------------------------------------------------------------

NEGATIVE_CASES: list[PlanningEvalCase] = [
    PlanningEvalCase(
        id="plan_neg_01",
        name="wrong start date",
        request=_req("Paris", "2025-06-01", "2025-06-01"),
        expected="fail",
        candidate_trip=_trip(
            "Paris",
            "2025-06-02",
            "2025-06-02",
            [_day("2025-06-02", [_act("Louvre", "09:00", "11:00")])],
        ),
        checks=[dates_match(_req("Paris", "2025-06-01", "2025-06-01"))],
    ),
    PlanningEvalCase(
        id="plan_neg_02",
        name="over budget",
        request=_req("NYC", "2025-06-01", "2025-06-01", budget="50"),
        expected="fail",
        candidate_trip=_trip(
            "NYC",
            "2025-06-01",
            "2025-06-01",
            [
                _day(
                    "2025-06-01",
                    [
                        _act("MoMA", "09:00", "11:00", cost="25"),
                        _act("Broadway Show", "19:00", "22:00", cost="150"),
                    ],
                )
            ],
        ),
        checks=[budget_respected(Decimal("50"))],
    ),
    PlanningEvalCase(
        id="plan_neg_03",
        name="overlapping activities",
        request=_req("Paris", "2025-06-01", "2025-06-01"),
        expected="fail",
        candidate_trip=_trip(
            "Paris",
            "2025-06-01",
            "2025-06-01",
            [
                _day(
                    "2025-06-01",
                    [
                        _act("Louvre", "09:00", "12:00"),
                        _act("Eiffel Tower", "11:00", "13:00"),
                    ],
                )
            ],
        ),
        checks=[no_overlapping_activities()],
    ),
    PlanningEvalCase(
        id="plan_neg_04",
        name="locked activity removed",
        request=_req(
            "Madrid",
            "2025-06-01",
            "2025-06-01",
            locked=[_act("Prado Museum", "10:00", "12:00", locked=True)],
        ),
        expected="fail",
        candidate_trip=_trip(
            "Madrid",
            "2025-06-01",
            "2025-06-01",
            [_day("2025-06-01", [_act("Retiro Park", "09:00", "11:00")])],
        ),
        checks=[
            locked_activities_present(
                [_act("Prado Museum", "10:00", "12:00", locked=True)]
            )
        ],
    ),
    PlanningEvalCase(
        id="plan_neg_05",
        name="missing day in multi-day trip",
        request=_req("Vienna", "2025-06-01", "2025-06-03"),
        expected="fail",
        candidate_trip=_trip(
            "Vienna",
            "2025-06-01",
            "2025-06-03",
            [
                _day("2025-06-01", [_act("Schoenbrunn Palace", "09:00", "11:00")]),
                _day("2025-06-03", [_act("St. Stephen's Cathedral", "10:00", "12:00")]),
            ],
        ),
        checks=[all_days_represented(_req("Vienna", "2025-06-01", "2025-06-03"))],
    ),
    PlanningEvalCase(
        id="plan_neg_06",
        name="no activities at all",
        request=_req("Lisbon", "2025-06-01", "2025-06-01"),
        expected="fail",
        candidate_trip=_trip(
            "Lisbon",
            "2025-06-01",
            "2025-06-01",
            [_day("2025-06-01", [])],
        ),
        checks=[has_activities()],
    ),
    PlanningEvalCase(
        id="plan_neg_07",
        name="wrong destination",
        request=_req("Prague", "2025-06-01", "2025-06-01"),
        expected="fail",
        candidate_trip=_trip(
            "Budapest",
            "2025-06-01",
            "2025-06-01",
            [_day("2025-06-01", [_act("Parliament", "09:00", "11:00")])],
        ),
        checks=[destination_preserved(_req("Prague", "2025-06-01", "2025-06-01"))],
    ),
    PlanningEvalCase(
        id="plan_neg_08",
        name="just over budget by one cent",
        request=_req("Zurich", "2025-06-01", "2025-06-01", budget="100"),
        expected="fail",
        candidate_trip=_trip(
            "Zurich",
            "2025-06-01",
            "2025-06-01",
            [_day("2025-06-01", [_act("Swiss Museum", "09:00", "11:00", cost="100.01")])],
        ),
        checks=[budget_respected(Decimal("100"))],
    ),
    PlanningEvalCase(
        id="plan_neg_09",
        name="wrong end date",
        request=_req("Paris", "2025-06-01", "2025-06-02"),
        expected="fail",
        candidate_trip=_trip(
            "Paris",
            "2025-06-01",
            "2025-06-03",
            [
                _day("2025-06-01", [_act("Louvre", "09:00", "11:00")]),
                _day("2025-06-02", [_act("Eiffel Tower", "09:00", "11:00")]),
                _day("2025-06-03", [_act("Versailles", "09:00", "11:00")]),
            ],
        ),
        checks=[dates_match(_req("Paris", "2025-06-01", "2025-06-02"))],
    ),
]

ALL_PLANNING_CASES: list[PlanningEvalCase] = POSITIVE_CASES + NEGATIVE_CASES
