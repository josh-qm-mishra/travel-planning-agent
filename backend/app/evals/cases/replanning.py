"""Fixture replanning eval cases — no live agent calls."""
from __future__ import annotations

from datetime import date, time
from decimal import Decimal

from ...models.trip import Activity, Trip, TripConstraints, TripDay
from ..checks import (
    affected_date_changed,
    budget_maintained,
    destination_unchanged,
    locked_preserved_after_replan,
    no_overlaps_after_replan,
    trip_dates_unchanged,
    unaffected_days_unchanged,
)
from ..models import ReplanEvalCase


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _day(d: str, acts: list[Activity]) -> TripDay:
    return TripDay(date=date.fromisoformat(d), activities=acts)


def _trip(destination: str, start: str, end: str, days: list[TripDay]) -> Trip:
    return Trip(
        destination=destination,
        start_date=date.fromisoformat(start),
        end_date=date.fromisoformat(end),
        days=days,
    )


# ---------------------------------------------------------------------------
# Base trips reused across cases
# ---------------------------------------------------------------------------

_PARIS_1DAY = _trip(
    "Paris",
    "2025-06-01",
    "2025-06-01",
    [
        _day(
            "2025-06-01",
            [
                _act("Louvre", "09:00", "11:00", cost="20"),
                _act("Eiffel Tower", "13:00", "15:00", cost="30"),
                _act("Seine Dinner", "19:00", "21:00", cost="60", locked=True),
            ],
        )
    ],
)

_PARIS_2DAY = _trip(
    "Paris",
    "2025-06-01",
    "2025-06-02",
    [
        _day(
            "2025-06-01",
            [
                _act("Louvre", "09:00", "11:00", cost="20"),
                _act("Eiffel Tower", "13:00", "15:00", cost="30"),
            ],
        ),
        _day(
            "2025-06-02",
            [
                _act("Sacre Coeur", "09:00", "11:00", cost="0"),
                _act("Musee d'Orsay", "13:00", "15:00", cost="15"),
            ],
        ),
    ],
)

_TOKYO_1DAY = _trip(
    "Tokyo",
    "2025-07-01",
    "2025-07-01",
    [
        _day(
            "2025-07-01",
            [
                _act("Senso-ji Temple", "09:00", "11:00"),
                _act("Shibuya Crossing", "13:00", "14:00"),
                _act("Omakase Dinner", "19:00", "21:00", cost="150", locked=True),
            ],
        )
    ],
)


# ---------------------------------------------------------------------------
# Positive cases (8): replanned trips that satisfy all checks
# ---------------------------------------------------------------------------

POSITIVE_CASES: list[ReplanEvalCase] = [
    ReplanEvalCase(
        id="replan_pos_01",
        name="simple activity replacement — day 1 changed",
        original_trip=_PARIS_2DAY,
        change_request="Replace Louvre with Versailles on day 1",
        candidate_trip=_trip(
            "Paris",
            "2025-06-01",
            "2025-06-02",
            [
                _day(
                    "2025-06-01",
                    [
                        _act("Versailles", "09:00", "11:00", cost="20"),
                        _act("Eiffel Tower", "13:00", "15:00", cost="30"),
                    ],
                ),
                _day(
                    "2025-06-02",
                    [
                        _act("Sacre Coeur", "09:00", "11:00", cost="0"),
                        _act("Musee d'Orsay", "13:00", "15:00", cost="15"),
                    ],
                ),
            ],
        ),
        checks=[
            destination_unchanged(),
            trip_dates_unchanged(),
            no_overlaps_after_replan(),
            affected_date_changed(date(2025, 6, 1)),
            unaffected_days_unchanged([date(2025, 6, 1)]),
        ],
    ),
    ReplanEvalCase(
        id="replan_pos_02",
        name="locked dinner preserved after replan",
        original_trip=_PARIS_1DAY,
        change_request="Replace Louvre with Versailles",
        candidate_trip=_trip(
            "Paris",
            "2025-06-01",
            "2025-06-01",
            [
                _day(
                    "2025-06-01",
                    [
                        _act("Versailles", "09:00", "11:00", cost="20"),
                        _act("Eiffel Tower", "13:00", "15:00", cost="30"),
                        _act("Seine Dinner", "19:00", "21:00", cost="60", locked=True),
                    ],
                )
            ],
        ),
        checks=[
            locked_preserved_after_replan(_PARIS_1DAY),
            no_overlaps_after_replan(),
        ],
    ),
    ReplanEvalCase(
        id="replan_pos_03",
        name="unaffected day 2 unchanged after day 1 change",
        original_trip=_PARIS_2DAY,
        change_request="Add a morning coffee stop on day 1",
        candidate_trip=_trip(
            "Paris",
            "2025-06-01",
            "2025-06-02",
            [
                _day(
                    "2025-06-01",
                    [
                        _act("Cafe de Flore Coffee", "08:00", "09:00", cost="10"),
                        _act("Louvre", "09:30", "11:30", cost="20"),
                        _act("Eiffel Tower", "13:00", "15:00", cost="30"),
                    ],
                ),
                _day(
                    "2025-06-02",
                    [
                        _act("Sacre Coeur", "09:00", "11:00", cost="0"),
                        _act("Musee d'Orsay", "13:00", "15:00", cost="15"),
                    ],
                ),
            ],
        ),
        checks=[
            unaffected_days_unchanged([date(2025, 6, 1)]),
            no_overlaps_after_replan(),
            destination_unchanged(),
            trip_dates_unchanged(),
        ],
    ),
    ReplanEvalCase(
        id="replan_pos_04",
        name="budget maintained after change",
        original_trip=_trip(
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
        change_request="Add Trevi Fountain visit in the afternoon",
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
                        _act("Trevi Fountain", "14:00", "15:00", cost="0"),
                    ],
                )
            ],
        ),
        checks=[
            budget_maintained(Decimal("200")),
            no_overlaps_after_replan(),
        ],
    ),
    ReplanEvalCase(
        id="replan_pos_05",
        name="multiple locked activities preserved",
        original_trip=_trip(
            "London",
            "2025-09-01",
            "2025-09-01",
            [
                _day(
                    "2025-09-01",
                    [
                        _act("British Museum", "09:00", "11:00", locked=True),
                        _act("Tower of London", "13:00", "15:00", locked=True),
                        _act("Borough Market", "15:30", "17:00"),
                    ],
                )
            ],
        ),
        change_request="Replace Borough Market with Tate Modern",
        candidate_trip=_trip(
            "London",
            "2025-09-01",
            "2025-09-01",
            [
                _day(
                    "2025-09-01",
                    [
                        _act("British Museum", "09:00", "11:00", locked=True),
                        _act("Tower of London", "13:00", "15:00", locked=True),
                        _act("Tate Modern", "15:30", "17:30"),
                    ],
                )
            ],
        ),
        checks=[
            locked_preserved_after_replan(
                _trip(
                    "London",
                    "2025-09-01",
                    "2025-09-01",
                    [
                        _day(
                            "2025-09-01",
                            [
                                _act("British Museum", "09:00", "11:00", locked=True),
                                _act("Tower of London", "13:00", "15:00", locked=True),
                                _act("Borough Market", "15:30", "17:00"),
                            ],
                        )
                    ],
                )
            ),
            no_overlaps_after_replan(),
        ],
    ),
    ReplanEvalCase(
        id="replan_pos_06",
        name="affected date changed — day 2 modified",
        original_trip=_PARIS_2DAY,
        change_request="Replace day 2 activities with a day trip to Versailles",
        candidate_trip=_trip(
            "Paris",
            "2025-06-01",
            "2025-06-02",
            [
                _day(
                    "2025-06-01",
                    [
                        _act("Louvre", "09:00", "11:00", cost="20"),
                        _act("Eiffel Tower", "13:00", "15:00", cost="30"),
                    ],
                ),
                _day(
                    "2025-06-02",
                    [_act("Versailles", "09:00", "17:00", cost="30")],
                ),
            ],
        ),
        checks=[
            affected_date_changed(date(2025, 6, 2)),
            destination_unchanged(),
            trip_dates_unchanged(),
            no_overlaps_after_replan(),
        ],
    ),
    ReplanEvalCase(
        id="replan_pos_07",
        name="destination unchanged after replan",
        original_trip=_TOKYO_1DAY,
        change_request="Replace Shibuya Crossing with Harajuku",
        candidate_trip=_trip(
            "Tokyo",
            "2025-07-01",
            "2025-07-01",
            [
                _day(
                    "2025-07-01",
                    [
                        _act("Senso-ji Temple", "09:00", "11:00"),
                        _act("Harajuku", "13:00", "15:00"),
                        _act("Omakase Dinner", "19:00", "21:00", cost="150", locked=True),
                    ],
                )
            ],
        ),
        checks=[
            destination_unchanged(),
            trip_dates_unchanged(),
            locked_preserved_after_replan(_TOKYO_1DAY),
        ],
    ),
    ReplanEvalCase(
        id="replan_pos_08",
        name="trip dates unchanged after modification",
        original_trip=_PARIS_2DAY,
        change_request="Swap Louvre and Sacre Coeur between days",
        candidate_trip=_trip(
            "Paris",
            "2025-06-01",
            "2025-06-02",
            [
                _day(
                    "2025-06-01",
                    [
                        _act("Sacre Coeur", "09:00", "11:00", cost="0"),
                        _act("Eiffel Tower", "13:00", "15:00", cost="30"),
                    ],
                ),
                _day(
                    "2025-06-02",
                    [
                        _act("Louvre", "09:00", "11:00", cost="20"),
                        _act("Musee d'Orsay", "13:00", "15:00", cost="15"),
                    ],
                ),
            ],
        ),
        checks=[
            trip_dates_unchanged(),
            destination_unchanged(),
            no_overlaps_after_replan(),
        ],
    ),
]


# ---------------------------------------------------------------------------
# Negative cases (8): replanned trips with violations checks must detect
# ---------------------------------------------------------------------------

NEGATIVE_CASES: list[ReplanEvalCase] = [
    ReplanEvalCase(
        id="replan_neg_01",
        name="locked dinner removed",
        original_trip=_PARIS_1DAY,
        change_request="Remove the Seine Dinner",
        expected="fail",
        candidate_trip=_trip(
            "Paris",
            "2025-06-01",
            "2025-06-01",
            [
                _day(
                    "2025-06-01",
                    [
                        _act("Louvre", "09:00", "11:00", cost="20"),
                        _act("Eiffel Tower", "13:00", "15:00", cost="30"),
                    ],
                )
            ],
        ),
        checks=[locked_preserved_after_replan(_PARIS_1DAY)],
    ),
    ReplanEvalCase(
        id="replan_neg_02",
        name="locked dinner time changed",
        original_trip=_PARIS_1DAY,
        change_request="Move the Seine Dinner earlier",
        expected="fail",
        candidate_trip=_trip(
            "Paris",
            "2025-06-01",
            "2025-06-01",
            [
                _day(
                    "2025-06-01",
                    [
                        _act("Louvre", "09:00", "11:00", cost="20"),
                        _act("Eiffel Tower", "13:00", "15:00", cost="30"),
                        _act("Seine Dinner", "17:00", "19:00", cost="60", locked=True),
                    ],
                )
            ],
        ),
        checks=[locked_preserved_after_replan(_PARIS_1DAY)],
    ),
    ReplanEvalCase(
        id="replan_neg_03",
        name="unaffected day 2 was changed",
        original_trip=_PARIS_2DAY,
        change_request="Add a cafe stop on day 1",
        expected="fail",
        candidate_trip=_trip(
            "Paris",
            "2025-06-01",
            "2025-06-02",
            [
                _day(
                    "2025-06-01",
                    [
                        _act("Cafe stop", "08:00", "09:00"),
                        _act("Louvre", "09:30", "11:30", cost="20"),
                        _act("Eiffel Tower", "13:00", "15:00", cost="30"),
                    ],
                ),
                _day(
                    "2025-06-02",
                    [
                        _act("Sacre Coeur", "09:00", "11:00", cost="0"),
                        _act("Notre Dame", "13:00", "15:00", cost="0"),
                    ],
                ),
            ],
        ),
        checks=[unaffected_days_unchanged([date(2025, 6, 1)])],
    ),
    ReplanEvalCase(
        id="replan_neg_04",
        name="overlap introduced after replan",
        original_trip=_PARIS_1DAY,
        change_request="Add a boat tour",
        expected="fail",
        candidate_trip=_trip(
            "Paris",
            "2025-06-01",
            "2025-06-01",
            [
                _day(
                    "2025-06-01",
                    [
                        _act("Louvre", "09:00", "12:00", cost="20"),
                        _act("Boat Tour", "11:00", "13:00", cost="25"),
                        _act("Eiffel Tower", "13:00", "15:00", cost="30"),
                        _act("Seine Dinner", "19:00", "21:00", cost="60", locked=True),
                    ],
                )
            ],
        ),
        checks=[no_overlaps_after_replan()],
    ),
    ReplanEvalCase(
        id="replan_neg_05",
        name="budget exceeded after replan",
        original_trip=_trip(
            "Rome",
            "2025-08-01",
            "2025-08-01",
            [
                _day("2025-08-01", [_act("Colosseum", "09:00", "11:00", cost="20")])
            ],
        ),
        change_request="Add expensive private tour",
        expected="fail",
        candidate_trip=_trip(
            "Rome",
            "2025-08-01",
            "2025-08-01",
            [
                _day(
                    "2025-08-01",
                    [
                        _act("Colosseum", "09:00", "11:00", cost="20"),
                        _act("Private Vatican Tour", "13:00", "17:00", cost="500"),
                    ],
                )
            ],
        ),
        checks=[budget_maintained(Decimal("100"))],
    ),
    ReplanEvalCase(
        id="replan_neg_06",
        name="destination changed after replan",
        original_trip=_PARIS_1DAY,
        change_request="Plan in Rome instead",
        expected="fail",
        candidate_trip=_trip(
            "Rome",
            "2025-06-01",
            "2025-06-01",
            [_day("2025-06-01", [_act("Colosseum", "09:00", "11:00")])],
        ),
        checks=[destination_unchanged()],
    ),
    ReplanEvalCase(
        id="replan_neg_07",
        name="trip dates changed after replan",
        original_trip=_PARIS_2DAY,
        change_request="Extend the trip by one day",
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
        checks=[trip_dates_unchanged()],
    ),
    ReplanEvalCase(
        id="replan_neg_08",
        name="expected day was not changed",
        original_trip=_PARIS_2DAY,
        change_request="Change all activities on day 2",
        expected="fail",
        candidate_trip=_PARIS_2DAY,  # identical — no change made
        checks=[affected_date_changed(date(2025, 6, 2))],
    ),
]

ALL_REPLANNING_CASES: list[ReplanEvalCase] = POSITIVE_CASES + NEGATIVE_CASES
