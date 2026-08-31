"""Factory functions that return deterministic check closures."""
from __future__ import annotations

from datetime import date, time
from decimal import Decimal

from ..agent.models import TripPlanRequest
from ..models.trip import Activity, Trip
from .models import CheckResult, PlanCheckFn, ReplanCheckFn


# ---------------------------------------------------------------------------
# Planning checks  (Trip) -> CheckResult
# ---------------------------------------------------------------------------


def dates_match(request: TripPlanRequest) -> PlanCheckFn:
    def _check(trip: Trip) -> CheckResult:
        if trip.start_date != request.start_date:
            return CheckResult(
                "dates_match",
                False,
                f"start_date {trip.start_date} != {request.start_date}",
            )
        if trip.end_date != request.end_date:
            return CheckResult(
                "dates_match",
                False,
                f"end_date {trip.end_date} != {request.end_date}",
            )
        return CheckResult("dates_match", True)

    return _check


def destination_preserved(request: TripPlanRequest) -> PlanCheckFn:
    def _check(trip: Trip) -> CheckResult:
        if trip.destination.lower() != request.destination.lower():
            return CheckResult(
                "destination_preserved",
                False,
                f"'{trip.destination}' != '{request.destination}'",
            )
        return CheckResult("destination_preserved", True)

    return _check


def no_overlapping_activities() -> PlanCheckFn:
    def _check(trip: Trip) -> CheckResult:
        for day in trip.days:
            acts = sorted(day.activities, key=lambda a: a.start_time)
            for i in range(len(acts) - 1):
                if acts[i].end_time > acts[i + 1].start_time:
                    return CheckResult(
                        "no_overlapping_activities",
                        False,
                        f"Overlap on {day.date}: '{acts[i].name}' ends {acts[i].end_time} "
                        f"but '{acts[i+1].name}' starts {acts[i+1].start_time}",
                    )
        return CheckResult("no_overlapping_activities", True)

    return _check


def budget_respected(max_budget: Decimal) -> PlanCheckFn:
    def _check(trip: Trip) -> CheckResult:
        total = sum(
            a.estimated_cost
            for day in trip.days
            for a in day.activities
        )
        if total > max_budget:
            return CheckResult(
                "budget_respected",
                False,
                f"Total cost {float(total):.2f} exceeds budget {float(max_budget):.2f}",
            )
        return CheckResult("budget_respected", True)

    return _check


def locked_activities_present(locked: list[Activity]) -> PlanCheckFn:
    def _check(trip: Trip) -> CheckResult:
        all_names = {a.name for day in trip.days for a in day.activities}
        for act in locked:
            if act.name not in all_names:
                return CheckResult(
                    "locked_activities_present",
                    False,
                    f"Locked activity '{act.name}' not found in trip",
                )
        return CheckResult("locked_activities_present", True)

    return _check


def all_days_represented(request: TripPlanRequest) -> PlanCheckFn:
    def _check(trip: Trip) -> CheckResult:
        expected_dates: set[date] = set()
        current = request.start_date
        while current <= request.end_date:
            expected_dates.add(current)
            current = date.fromordinal(current.toordinal() + 1)

        trip_dates = {day.date for day in trip.days}
        missing = expected_dates - trip_dates
        if missing:
            missing_str = ", ".join(str(d) for d in sorted(missing))
            return CheckResult(
                "all_days_represented",
                False,
                f"Missing days: {missing_str}",
            )
        return CheckResult("all_days_represented", True)

    return _check


def has_activities() -> PlanCheckFn:
    def _check(trip: Trip) -> CheckResult:
        total = sum(len(day.activities) for day in trip.days)
        if total == 0:
            return CheckResult("has_activities", False, "Trip has no activities")
        return CheckResult("has_activities", True)

    return _check


# ---------------------------------------------------------------------------
# Replanning checks  (original: Trip, updated: Trip) -> CheckResult
# ---------------------------------------------------------------------------


def locked_preserved_after_replan(original_trip: Trip) -> ReplanCheckFn:
    def _check(original: Trip, updated: Trip) -> CheckResult:
        locked_acts = [
            a for day in original_trip.days for a in day.activities if a.locked
        ]
        all_updated = {a.name: a for day in updated.days for a in day.activities}
        for act in locked_acts:
            updated_act = all_updated.get(act.name)
            if updated_act is None:
                return CheckResult(
                    "locked_preserved_after_replan",
                    False,
                    f"Locked activity '{act.name}' was removed",
                )
            if updated_act.start_time != act.start_time or updated_act.end_time != act.end_time:
                return CheckResult(
                    "locked_preserved_after_replan",
                    False,
                    f"Locked activity '{act.name}' time changed: "
                    f"{act.start_time}-{act.end_time} → "
                    f"{updated_act.start_time}-{updated_act.end_time}",
                )
        return CheckResult("locked_preserved_after_replan", True)

    return _check


def unaffected_days_unchanged(excluded_dates: list[date]) -> ReplanCheckFn:
    """All days NOT in excluded_dates must have the same activity names."""

    def _check(original: Trip, updated: Trip) -> CheckResult:
        orig_by_date = {day.date: day for day in original.days}
        upd_by_date = {day.date: day for day in updated.days}

        for d, orig_day in orig_by_date.items():
            if d in excluded_dates:
                continue
            upd_day = upd_by_date.get(d)
            orig_names = sorted(a.name for a in orig_day.activities)
            upd_names = sorted(a.name for a in upd_day.activities) if upd_day else []
            if orig_names != upd_names:
                return CheckResult(
                    "unaffected_days_unchanged",
                    False,
                    f"Day {d} changed: {orig_names} → {upd_names}",
                )
        return CheckResult("unaffected_days_unchanged", True)

    return _check


def affected_date_changed(expected_date: date) -> ReplanCheckFn:
    """The specified date must have different activities after replanning."""

    def _check(original: Trip, updated: Trip) -> CheckResult:
        orig_day = next((d for d in original.days if d.date == expected_date), None)
        upd_day = next((d for d in updated.days if d.date == expected_date), None)
        orig_names = sorted(a.name for a in orig_day.activities) if orig_day else []
        upd_names = sorted(a.name for a in upd_day.activities) if upd_day else []
        if orig_names == upd_names:
            return CheckResult(
                "affected_date_changed",
                False,
                f"Day {expected_date} was not modified as expected",
            )
        return CheckResult("affected_date_changed", True)

    return _check


def no_overlaps_after_replan() -> ReplanCheckFn:
    def _check(original: Trip, updated: Trip) -> CheckResult:
        for day in updated.days:
            acts = sorted(day.activities, key=lambda a: a.start_time)
            for i in range(len(acts) - 1):
                if acts[i].end_time > acts[i + 1].start_time:
                    return CheckResult(
                        "no_overlaps_after_replan",
                        False,
                        f"Overlap on {day.date}: '{acts[i].name}' ends {acts[i].end_time} "
                        f"but '{acts[i+1].name}' starts {acts[i+1].start_time}",
                    )
        return CheckResult("no_overlaps_after_replan", True)

    return _check


def budget_maintained(max_budget: Decimal) -> ReplanCheckFn:
    def _check(original: Trip, updated: Trip) -> CheckResult:
        total = sum(
            a.estimated_cost for day in updated.days for a in day.activities
        )
        if total > max_budget:
            return CheckResult(
                "budget_maintained",
                False,
                f"Updated trip cost {float(total):.2f} exceeds budget {float(max_budget):.2f}",
            )
        return CheckResult("budget_maintained", True)

    return _check


def destination_unchanged() -> ReplanCheckFn:
    def _check(original: Trip, updated: Trip) -> CheckResult:
        if original.destination.lower() != updated.destination.lower():
            return CheckResult(
                "destination_unchanged",
                False,
                f"Destination changed: '{original.destination}' → '{updated.destination}'",
            )
        return CheckResult("destination_unchanged", True)

    return _check


def trip_dates_unchanged() -> ReplanCheckFn:
    def _check(original: Trip, updated: Trip) -> CheckResult:
        if original.start_date != updated.start_date or original.end_date != updated.end_date:
            return CheckResult(
                "trip_dates_unchanged",
                False,
                f"Trip dates changed: {original.start_date}–{original.end_date} → "
                f"{updated.start_date}–{updated.end_date}",
            )
        return CheckResult("trip_dates_unchanged", True)

    return _check
