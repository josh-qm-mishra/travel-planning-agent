"""Deterministic itinerary validator.

This module is pure Python — no LLM calls.  It can be used independently of
the agent for testing, CI checks, or future API validation endpoints.

validate_itinerary() is the main entry point.

Travel-feasibility checking (check_routing=True) is opt-in because it makes
async tool calls (geocoding + routing) and adds latency.  The standard
validation pass uses a simpler gap-based heuristic instead.

Transition buffer assumption
----------------------------
When routing IS used (check_routing=True), we add TRANSITION_BUFFER_SECONDS
(10 min) to the raw routing travel time to account for walking to the exit,
buying tickets, etc.  This value is module-level so callers can override it
in tests if needed.
"""

from dataclasses import dataclass, field
from datetime import date, time
from decimal import Decimal

from ..models.trip import Activity, Trip
from ..tools.exceptions import GeocodingError, RoutingError
from ..tools.geocoding import geocode_location
from ..tools.models import TravelMode
from ..tools.routing import get_route

TRANSITION_BUFFER_SECONDS: int = 600  # 10 minutes
_MIN_GAP_WARNING_SECONDS: int = 600   # gaps < 10 min → warning


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class ValidationIssue:
    rule: str
    message: str
    severity: str = "error"   # "error" | "warning"
    day: str | None = None
    activity: str | None = None


@dataclass
class ValidationResult:
    valid: bool
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "warning"]


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def validate_itinerary(
    trip: Trip,
    original_trip: Trip | None = None,
    check_routing: bool = False,
) -> ValidationResult:
    """Run all validation rules against *trip*.

    Args:
        trip: Itinerary to validate.
        original_trip: When provided, locked-activity preservation is checked.
        check_routing: If True, use the routing API to verify travel
            feasibility between consecutive activities.  This makes async
            tool calls — leave False for fast in-process validation.
    """
    issues: list[ValidationIssue] = []

    _check_schedule(trip, issues)

    if original_trip is not None:
        _check_locked_activities(trip, original_trip, issues)

    _check_budget(trip, issues)

    if check_routing:
        await _check_travel_feasibility(trip, issues)
    else:
        _check_travel_gaps(trip, issues)

    return ValidationResult(
        valid=not any(i.severity == "error" for i in issues),
        issues=issues,
    )


# ---------------------------------------------------------------------------
# Rule: A — schedule overlap
# ---------------------------------------------------------------------------


def _check_schedule(trip: Trip, issues: list[ValidationIssue]) -> None:
    for day in trip.days:
        sorted_acts = sorted(day.activities, key=lambda a: a.start_time)
        for i in range(len(sorted_acts) - 1):
            curr = sorted_acts[i]
            nxt = sorted_acts[i + 1]
            if curr.end_time > nxt.start_time:
                issues.append(
                    ValidationIssue(
                        rule="schedule.overlap",
                        message=(
                            f"On {day.date}: '{curr.name}' ends at {curr.end_time} "
                            f"but '{nxt.name}' starts at {nxt.start_time} — overlap"
                        ),
                        severity="error",
                        day=str(day.date),
                        activity=curr.name,
                    )
                )


# ---------------------------------------------------------------------------
# Rule: B — locked-activity preservation
# ---------------------------------------------------------------------------


def _check_locked_activities(
    trip: Trip,
    original_trip: Trip,
    issues: list[ValidationIssue],
) -> None:
    # Index original locked activities: name → (date_str, start_str, end_str)
    orig_locked: dict[str, tuple[str, str, str]] = {}
    for day in original_trip.days:
        for act in day.activities:
            if act.locked:
                orig_locked[act.name] = (
                    str(day.date),
                    str(act.start_time),
                    str(act.end_time),
                )

    # Index new trip's activities (all of them, not just locked)
    new_index: dict[str, tuple[str, str, str]] = {}
    for day in trip.days:
        for act in day.activities:
            new_index[act.name] = (
                str(day.date),
                str(act.start_time),
                str(act.end_time),
            )

    for name, (orig_date, orig_start, orig_end) in orig_locked.items():
        if name not in new_index:
            issues.append(
                ValidationIssue(
                    rule="locked.removed",
                    message=f"Locked activity '{name}' was removed",
                    severity="error",
                    activity=name,
                )
            )
        else:
            new_date, new_start, new_end = new_index[name]
            if new_date != orig_date or new_start != orig_start or new_end != orig_end:
                issues.append(
                    ValidationIssue(
                        rule="locked.modified",
                        message=(
                            f"Locked activity '{name}' was modified: "
                            f"was {orig_date} {orig_start}–{orig_end}, "
                            f"now {new_date} {new_start}–{new_end}"
                        ),
                        severity="error",
                        activity=name,
                    )
                )


# ---------------------------------------------------------------------------
# Rule: C — budget
# ---------------------------------------------------------------------------


def _check_budget(trip: Trip, issues: list[ValidationIssue]) -> None:
    # Use the tighter of total_budget and constraints.maximum_budget.
    budget: Decimal | None = None
    if trip.total_budget is not None:
        budget = trip.total_budget
    if trip.constraints.maximum_budget is not None:
        if budget is None or trip.constraints.maximum_budget < budget:
            budget = trip.constraints.maximum_budget

    if budget is None:
        return

    total_known = sum(
        a.estimated_cost for day in trip.days for a in day.activities
    )

    if total_known > budget:
        issues.append(
            ValidationIssue(
                rule="budget.exceeded",
                message=(
                    f"Total estimated cost ${float(total_known):.2f} exceeds "
                    f"budget ${float(budget):.2f}"
                ),
                severity="error",
            )
        )


# ---------------------------------------------------------------------------
# Rule: D (fast) — gap heuristic
# ---------------------------------------------------------------------------


def _check_travel_gaps(trip: Trip, issues: list[ValidationIssue]) -> None:
    """Flag suspiciously tight gaps (< 10 min) between consecutive activities."""
    for day in trip.days:
        sorted_acts = sorted(day.activities, key=lambda a: a.start_time)
        for i in range(len(sorted_acts) - 1):
            curr = sorted_acts[i]
            nxt = sorted_acts[i + 1]
            gap = _time_to_s(nxt.start_time) - _time_to_s(curr.end_time)
            if 0 < gap < _MIN_GAP_WARNING_SECONDS:
                issues.append(
                    ValidationIssue(
                        rule="travel.tight_gap",
                        message=(
                            f"On {day.date}: only {gap // 60}m gap between "
                            f"'{curr.name}' and '{nxt.name}'"
                        ),
                        severity="warning",
                        day=str(day.date),
                        activity=curr.name,
                    )
                )


# ---------------------------------------------------------------------------
# Rule: D (full) ��� routing-based feasibility
# ---------------------------------------------------------------------------


async def _check_travel_feasibility(
    trip: Trip, issues: list[ValidationIssue]
) -> None:
    """Use geocoding + routing to verify consecutive-activity transitions.

    Pairs where geocoding fails are silently skipped — we only flag what we
    can determine with confidence.
    """
    for day in trip.days:
        sorted_acts = sorted(day.activities, key=lambda a: a.start_time)
        for i in range(len(sorted_acts) - 1):
            curr = sorted_acts[i]
            nxt = sorted_acts[i + 1]

            gap = _time_to_s(nxt.start_time) - _time_to_s(curr.end_time)
            if gap <= 0:
                continue  # Overlap already handled by schedule check.

            try:
                loc_curr = await geocode_location(curr.location)
                loc_nxt = await geocode_location(nxt.location)
            except GeocodingError:
                continue  # No usable coordinates — skip this pair.

            try:
                route = await get_route(
                    origin_lat=loc_curr.latitude,
                    origin_lng=loc_curr.longitude,
                    destination_lat=loc_nxt.latitude,
                    destination_lng=loc_nxt.longitude,
                    travel_mode=TravelMode.WALK,
                )
            except RoutingError:
                continue  # Routing unavailable — skip.

            needed = route.duration_seconds + TRANSITION_BUFFER_SECONDS
            if needed > gap:
                issues.append(
                    ValidationIssue(
                        rule="travel.infeasible",
                        message=(
                            f"On {day.date}: insufficient time between "
                            f"'{curr.name}' and '{nxt.name}' — "
                            f"{route.duration_seconds // 60}m walk "
                            f"+ {TRANSITION_BUFFER_SECONDS // 60}m buffer "
                            f"> {gap // 60}m gap"
                        ),
                        severity="error",
                        day=str(day.date),
                        activity=curr.name,
                    )
                )


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def _time_to_s(t: time) -> int:
    return t.hour * 3600 + t.minute * 60 + t.second
