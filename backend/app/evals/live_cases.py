"""Live eval cases — candidate_trip=None means the runner calls the real agent."""
from __future__ import annotations

from datetime import date, time
from decimal import Decimal

from ..agent.models import TripPlanRequest
from ..models.trip import Activity, Trip, TripConstraints, TripDay
from .checks import (
    all_days_represented,
    budget_respected,
    dates_match,
    destination_preserved,
    has_activities,
    locked_preserved_after_replan,
    no_overlapping_activities,
    no_overlaps_after_replan,
    trip_dates_unchanged,
)
from .models import PlanningEvalCase, ReplanEvalCase


def _act(name: str, start: str, end: str, cost: str = "0", locked: bool = False) -> Activity:
    return Activity(
        name=name,
        location="Somewhere",
        start_time=time.fromisoformat(start),
        end_time=time.fromisoformat(end),
        estimated_cost=Decimal(cost),
        category="sightseeing",
        locked=locked,
    )


def _day(d: str, acts: list[Activity]) -> TripDay:
    return TripDay(date=date.fromisoformat(d), activities=acts)


def _trip(destination: str, start: str, end: str, days: list[TripDay]) -> Trip:
    return Trip(
        destination=destination,
        start_date=date.fromisoformat(start),
        end_date=date.fromisoformat(end),
        days=days,
    )


_PARIS_REQ_1DAY = TripPlanRequest(
    destination="Paris",
    start_date=date(2025, 6, 1),
    end_date=date(2025, 6, 1),
)

_PARIS_REQ_BUDGET = TripPlanRequest(
    destination="Paris",
    start_date=date(2025, 6, 1),
    end_date=date(2025, 6, 1),
    total_budget=Decimal("200"),
    constraints=TripConstraints(maximum_budget=Decimal("200")),
)

_TOKYO_REQ_1DAY = TripPlanRequest(
    destination="Tokyo",
    start_date=date(2025, 7, 1),
    end_date=date(2025, 7, 1),
)

# Trip used as base for live replanning cases
_LIVE_REPLAN_BASE = _trip(
    "Paris",
    "2025-06-01",
    "2025-06-01",
    [
        _day(
            "2025-06-01",
            [
                _act("Louvre", "09:00", "11:00", cost="20"),
                _act("Eiffel Tower", "13:00", "15:00", cost="30"),
                _act("Seine River Dinner", "19:00", "21:00", cost="60", locked=True),
            ],
        )
    ],
)

LIVE_PLANNING_CASES: list[PlanningEvalCase] = [
    PlanningEvalCase(
        id="live_plan_01",
        name="1-day Paris basics",
        request=_PARIS_REQ_1DAY,
        candidate_trip=None,
        checks=[
            dates_match(_PARIS_REQ_1DAY),
            destination_preserved(_PARIS_REQ_1DAY),
            no_overlapping_activities(),
            has_activities(),
            all_days_represented(_PARIS_REQ_1DAY),
        ],
    ),
    PlanningEvalCase(
        id="live_plan_02",
        name="1-day Paris with $200 budget",
        request=_PARIS_REQ_BUDGET,
        candidate_trip=None,
        checks=[
            dates_match(_PARIS_REQ_BUDGET),
            destination_preserved(_PARIS_REQ_BUDGET),
            budget_respected(Decimal("200")),
            no_overlapping_activities(),
        ],
    ),
    PlanningEvalCase(
        id="live_plan_03",
        name="1-day Tokyo",
        request=_TOKYO_REQ_1DAY,
        candidate_trip=None,
        checks=[
            dates_match(_TOKYO_REQ_1DAY),
            destination_preserved(_TOKYO_REQ_1DAY),
            no_overlapping_activities(),
            has_activities(),
        ],
    ),
]

LIVE_REPLANNING_CASES: list[ReplanEvalCase] = [
    ReplanEvalCase(
        id="live_replan_01",
        name="add activity — locked dinner preserved",
        original_trip=_LIVE_REPLAN_BASE,
        change_request="Add a morning pastry stop before the Louvre",
        candidate_trip=None,
        checks=[
            locked_preserved_after_replan(_LIVE_REPLAN_BASE),
            no_overlaps_after_replan(),
            trip_dates_unchanged(),
        ],
    ),
    ReplanEvalCase(
        id="live_replan_02",
        name="weather disruption — outdoor to indoor swap",
        original_trip=_LIVE_REPLAN_BASE,
        change_request="It's raining. Replace outdoor activities with indoor alternatives, "
        "but keep the locked Seine River Dinner.",
        candidate_trip=None,
        checks=[
            locked_preserved_after_replan(_LIVE_REPLAN_BASE),
            no_overlaps_after_replan(),
            trip_dates_unchanged(),
        ],
    ),
]

ALL_LIVE_CASES: list[PlanningEvalCase | ReplanEvalCase] = (
    LIVE_PLANNING_CASES + LIVE_REPLANNING_CASES  # type: ignore[list-item]
)
