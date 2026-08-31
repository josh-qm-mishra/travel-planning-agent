"""Tests for the eval framework — checks, runner, and aggregate metrics."""
from __future__ import annotations

from datetime import date, time
from decimal import Decimal

import pytest

from app.agent.models import TripPlanRequest
from app.evals.cases import ALL_PLANNING_CASES, ALL_REPLANNING_CASES
from app.evals.checks import (
    affected_date_changed,
    all_days_represented,
    budget_maintained,
    budget_respected,
    dates_match,
    destination_preserved,
    destination_unchanged,
    has_activities,
    locked_activities_present,
    locked_preserved_after_replan,
    no_overlapping_activities,
    no_overlaps_after_replan,
    trip_dates_unchanged,
    unaffected_days_unchanged,
)
from app.evals.models import (
    AggregateReport,
    CaseResult,
    CheckResult,
    PlanningEvalCase,
    ReplanEvalCase,
)
from app.evals.runner import (
    build_report,
    run_offline_evals,
    run_planning_case,
    run_replanning_case,
)
from app.models.trip import Activity, Trip, TripConstraints, TripDay


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _act(
    name: str,
    start: str,
    end: str,
    cost: str = "0",
    locked: bool = False,
) -> Activity:
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


def _req(destination: str = "Paris", start: str = "2025-06-01", end: str = "2025-06-01") -> TripPlanRequest:
    return TripPlanRequest(
        destination=destination,
        start_date=date.fromisoformat(start),
        end_date=date.fromisoformat(end),
    )


# ---------------------------------------------------------------------------
# Planning check unit tests
# ---------------------------------------------------------------------------


class TestDatesMatch:
    def test_pass_when_dates_correct(self):
        req = _req("Paris", "2025-06-01", "2025-06-02")
        trip = _trip("Paris", "2025-06-01", "2025-06-02", [])
        assert dates_match(req)(trip).passed

    def test_fail_wrong_start(self):
        req = _req("Paris", "2025-06-01", "2025-06-01")
        trip = _trip("Paris", "2025-06-02", "2025-06-02", [])
        result = dates_match(req)(trip)
        assert not result.passed
        assert "start_date" in result.reason

    def test_fail_wrong_end(self):
        req = _req("Paris", "2025-06-01", "2025-06-02")
        trip = _trip("Paris", "2025-06-01", "2025-06-03", [])
        result = dates_match(req)(trip)
        assert not result.passed
        assert "end_date" in result.reason


class TestDestinationPreserved:
    def test_pass_exact_match(self):
        req = _req("Paris")
        trip = _trip("Paris", "2025-06-01", "2025-06-01", [])
        assert destination_preserved(req)(trip).passed

    def test_pass_case_insensitive(self):
        req = _req("paris")
        trip = _trip("PARIS", "2025-06-01", "2025-06-01", [])
        assert destination_preserved(req)(trip).passed

    def test_fail_different_city(self):
        req = _req("Paris")
        trip = _trip("Rome", "2025-06-01", "2025-06-01", [])
        result = destination_preserved(req)(trip)
        assert not result.passed


class TestNoOverlappingActivities:
    def test_pass_no_activities(self):
        trip = _trip("Paris", "2025-06-01", "2025-06-01", [_day("2025-06-01", [])])
        assert no_overlapping_activities()(trip).passed

    def test_pass_sequential(self):
        trip = _trip(
            "Paris",
            "2025-06-01",
            "2025-06-01",
            [_day("2025-06-01", [_act("A", "09:00", "11:00"), _act("B", "11:00", "13:00")])],
        )
        assert no_overlapping_activities()(trip).passed

    def test_fail_overlap(self):
        trip = _trip(
            "Paris",
            "2025-06-01",
            "2025-06-01",
            [_day("2025-06-01", [_act("A", "09:00", "12:00"), _act("B", "11:00", "13:00")])],
        )
        result = no_overlapping_activities()(trip)
        assert not result.passed
        assert "Overlap" in result.reason


class TestBudgetRespected:
    def test_pass_under_budget(self):
        trip = _trip(
            "Paris",
            "2025-06-01",
            "2025-06-01",
            [_day("2025-06-01", [_act("A", "09:00", "11:00", cost="50")])],
        )
        assert budget_respected(Decimal("100"))(trip).passed

    def test_pass_exact_budget(self):
        trip = _trip(
            "Paris",
            "2025-06-01",
            "2025-06-01",
            [_day("2025-06-01", [_act("A", "09:00", "11:00", cost="100")])],
        )
        assert budget_respected(Decimal("100"))(trip).passed

    def test_fail_over_budget(self):
        trip = _trip(
            "Paris",
            "2025-06-01",
            "2025-06-01",
            [_day("2025-06-01", [_act("A", "09:00", "11:00", cost="100.01")])],
        )
        result = budget_respected(Decimal("100"))(trip)
        assert not result.passed
        assert "exceeds" in result.reason


class TestLockedActivitiesPresent:
    def test_pass_locked_present(self):
        locked = [_act("Dinner", "19:00", "21:00", locked=True)]
        trip = _trip(
            "Paris",
            "2025-06-01",
            "2025-06-01",
            [_day("2025-06-01", [_act("A", "09:00", "11:00"), _act("Dinner", "19:00", "21:00", locked=True)])],
        )
        assert locked_activities_present(locked)(trip).passed

    def test_fail_locked_missing(self):
        locked = [_act("Dinner", "19:00", "21:00", locked=True)]
        trip = _trip(
            "Paris",
            "2025-06-01",
            "2025-06-01",
            [_day("2025-06-01", [_act("A", "09:00", "11:00")])],
        )
        result = locked_activities_present(locked)(trip)
        assert not result.passed
        assert "Dinner" in result.reason


class TestAllDaysRepresented:
    def test_pass_all_days_present(self):
        req = _req("Paris", "2025-06-01", "2025-06-03")
        trip = _trip(
            "Paris",
            "2025-06-01",
            "2025-06-03",
            [
                _day("2025-06-01", []),
                _day("2025-06-02", []),
                _day("2025-06-03", []),
            ],
        )
        assert all_days_represented(req)(trip).passed

    def test_fail_missing_day(self):
        req = _req("Paris", "2025-06-01", "2025-06-03")
        trip = _trip(
            "Paris",
            "2025-06-01",
            "2025-06-03",
            [_day("2025-06-01", []), _day("2025-06-03", [])],
        )
        result = all_days_represented(req)(trip)
        assert not result.passed
        assert "2025-06-02" in result.reason


class TestHasActivities:
    def test_pass_with_activities(self):
        trip = _trip(
            "Paris",
            "2025-06-01",
            "2025-06-01",
            [_day("2025-06-01", [_act("A", "09:00", "11:00")])],
        )
        assert has_activities()(trip).passed

    def test_fail_empty(self):
        trip = _trip("Paris", "2025-06-01", "2025-06-01", [_day("2025-06-01", [])])
        result = has_activities()(trip)
        assert not result.passed


# ---------------------------------------------------------------------------
# Replanning check unit tests
# ---------------------------------------------------------------------------


class TestLockedPreservedAfterReplan:
    def _base_trip(self) -> Trip:
        return _trip(
            "Paris",
            "2025-06-01",
            "2025-06-01",
            [
                _day(
                    "2025-06-01",
                    [
                        _act("Louvre", "09:00", "11:00"),
                        _act("Dinner", "19:00", "21:00", locked=True),
                    ],
                )
            ],
        )

    def test_pass_locked_preserved(self):
        base = self._base_trip()
        updated = _trip(
            "Paris",
            "2025-06-01",
            "2025-06-01",
            [
                _day(
                    "2025-06-01",
                    [
                        _act("Versailles", "09:00", "11:00"),
                        _act("Dinner", "19:00", "21:00", locked=True),
                    ],
                )
            ],
        )
        assert locked_preserved_after_replan(base)(base, updated).passed

    def test_fail_locked_removed(self):
        base = self._base_trip()
        updated = _trip(
            "Paris",
            "2025-06-01",
            "2025-06-01",
            [_day("2025-06-01", [_act("Versailles", "09:00", "11:00")])],
        )
        result = locked_preserved_after_replan(base)(base, updated)
        assert not result.passed
        assert "removed" in result.reason

    def test_fail_locked_time_changed(self):
        base = self._base_trip()
        updated = _trip(
            "Paris",
            "2025-06-01",
            "2025-06-01",
            [
                _day(
                    "2025-06-01",
                    [
                        _act("Louvre", "09:00", "11:00"),
                        _act("Dinner", "18:00", "20:00", locked=True),
                    ],
                )
            ],
        )
        result = locked_preserved_after_replan(base)(base, updated)
        assert not result.passed
        assert "time changed" in result.reason


class TestUnaffectedDaysUnchanged:
    def test_pass_unaffected_day_same(self):
        original = _trip(
            "Paris",
            "2025-06-01",
            "2025-06-02",
            [
                _day("2025-06-01", [_act("Louvre", "09:00", "11:00")]),
                _day("2025-06-02", [_act("Eiffel", "09:00", "11:00")]),
            ],
        )
        updated = _trip(
            "Paris",
            "2025-06-01",
            "2025-06-02",
            [
                _day("2025-06-01", [_act("Versailles", "09:00", "11:00")]),
                _day("2025-06-02", [_act("Eiffel", "09:00", "11:00")]),
            ],
        )
        # day 1 is excluded (changed), day 2 must be same
        check = unaffected_days_unchanged([date(2025, 6, 1)])
        assert check(original, updated).passed

    def test_fail_unaffected_day_changed(self):
        original = _trip(
            "Paris",
            "2025-06-01",
            "2025-06-02",
            [
                _day("2025-06-01", [_act("Louvre", "09:00", "11:00")]),
                _day("2025-06-02", [_act("Eiffel", "09:00", "11:00")]),
            ],
        )
        updated = _trip(
            "Paris",
            "2025-06-01",
            "2025-06-02",
            [
                _day("2025-06-01", [_act("Versailles", "09:00", "11:00")]),
                _day("2025-06-02", [_act("Notre Dame", "09:00", "11:00")]),
            ],
        )
        check = unaffected_days_unchanged([date(2025, 6, 1)])
        result = check(original, updated)
        assert not result.passed
        assert "2025-06-02" in result.reason


class TestAffectedDateChanged:
    def test_pass_date_changed(self):
        original = _trip(
            "Paris",
            "2025-06-01",
            "2025-06-01",
            [_day("2025-06-01", [_act("Louvre", "09:00", "11:00")])],
        )
        updated = _trip(
            "Paris",
            "2025-06-01",
            "2025-06-01",
            [_day("2025-06-01", [_act("Versailles", "09:00", "11:00")])],
        )
        assert affected_date_changed(date(2025, 6, 1))(original, updated).passed

    def test_fail_date_unchanged(self):
        original = _trip(
            "Paris",
            "2025-06-01",
            "2025-06-01",
            [_day("2025-06-01", [_act("Louvre", "09:00", "11:00")])],
        )
        result = affected_date_changed(date(2025, 6, 1))(original, original)
        assert not result.passed


class TestNoOverlapsAfterReplan:
    def test_pass_no_overlaps(self):
        original = _trip("Paris", "2025-06-01", "2025-06-01", [])
        updated = _trip(
            "Paris",
            "2025-06-01",
            "2025-06-01",
            [_day("2025-06-01", [_act("A", "09:00", "11:00"), _act("B", "12:00", "14:00")])],
        )
        assert no_overlaps_after_replan()(original, updated).passed

    def test_fail_overlap_introduced(self):
        original = _trip("Paris", "2025-06-01", "2025-06-01", [])
        updated = _trip(
            "Paris",
            "2025-06-01",
            "2025-06-01",
            [_day("2025-06-01", [_act("A", "09:00", "12:00"), _act("B", "11:00", "13:00")])],
        )
        result = no_overlaps_after_replan()(original, updated)
        assert not result.passed


class TestBudgetMaintained:
    def test_pass_under_budget(self):
        original = _trip("Paris", "2025-06-01", "2025-06-01", [])
        updated = _trip(
            "Paris",
            "2025-06-01",
            "2025-06-01",
            [_day("2025-06-01", [_act("A", "09:00", "11:00", cost="50")])],
        )
        assert budget_maintained(Decimal("100"))(original, updated).passed

    def test_fail_over_budget(self):
        original = _trip("Paris", "2025-06-01", "2025-06-01", [])
        updated = _trip(
            "Paris",
            "2025-06-01",
            "2025-06-01",
            [_day("2025-06-01", [_act("A", "09:00", "11:00", cost="200")])],
        )
        result = budget_maintained(Decimal("100"))(original, updated)
        assert not result.passed


class TestDestinationUnchanged:
    def test_pass_same_destination(self):
        original = _trip("Paris", "2025-06-01", "2025-06-01", [])
        updated = _trip("Paris", "2025-06-01", "2025-06-01", [])
        assert destination_unchanged()(original, updated).passed

    def test_fail_changed_destination(self):
        original = _trip("Paris", "2025-06-01", "2025-06-01", [])
        updated = _trip("Rome", "2025-06-01", "2025-06-01", [])
        result = destination_unchanged()(original, updated)
        assert not result.passed


class TestTripDatesUnchanged:
    def test_pass_same_dates(self):
        original = _trip("Paris", "2025-06-01", "2025-06-02", [])
        updated = _trip("Paris", "2025-06-01", "2025-06-02", [])
        assert trip_dates_unchanged()(original, updated).passed

    def test_fail_end_date_changed(self):
        original = _trip("Paris", "2025-06-01", "2025-06-02", [])
        updated = _trip("Paris", "2025-06-01", "2025-06-03", [])
        result = trip_dates_unchanged()(original, updated)
        assert not result.passed


# ---------------------------------------------------------------------------
# Runner tests
# ---------------------------------------------------------------------------


class TestRunPlanningCase:
    def _make_case(self, trip: Trip, checks, expected: str = "pass") -> PlanningEvalCase:
        return PlanningEvalCase(
            id="test_case",
            name="test",
            request=_req(),
            candidate_trip=trip,
            checks=checks,
            expected=expected,
        )

    def test_all_checks_pass(self):
        trip = _trip(
            "Paris",
            "2025-06-01",
            "2025-06-01",
            [_day("2025-06-01", [_act("A", "09:00", "11:00")])],
        )
        case = self._make_case(trip, [has_activities(), no_overlapping_activities()])
        result = run_planning_case(case)
        assert result.passed
        assert len(result.checks) == 2

    def test_one_check_fails(self):
        trip = _trip("Paris", "2025-06-01", "2025-06-01", [_day("2025-06-01", [])])
        case = self._make_case(trip, [has_activities()])
        result = run_planning_case(case)
        assert not result.passed

    def test_category_is_planning(self):
        trip = _trip("Paris", "2025-06-01", "2025-06-01", [])
        case = self._make_case(trip, [])
        result = run_planning_case(case)
        assert result.category == "planning"

    def test_expected_propagated_to_result(self):
        trip = _trip("Paris", "2025-06-01", "2025-06-01", [])
        case = self._make_case(trip, [], expected="fail")
        result = run_planning_case(case)
        assert result.expected == "fail"

    def test_expectation_met_positive(self):
        trip = _trip(
            "Paris", "2025-06-01", "2025-06-01",
            [_day("2025-06-01", [_act("A", "09:00", "11:00")])],
        )
        case = self._make_case(trip, [has_activities()], expected="pass")
        result = run_planning_case(case)
        assert result.expectation_met

    def test_expectation_met_negative(self):
        trip = _trip("Paris", "2025-06-01", "2025-06-01", [_day("2025-06-01", [])])
        case = self._make_case(trip, [has_activities()], expected="fail")
        result = run_planning_case(case)
        assert result.expectation_met  # check failed as expected


class TestRunReplanningCase:
    def _make_case(self, original: Trip, updated: Trip, checks, expected: str = "pass") -> ReplanEvalCase:
        return ReplanEvalCase(
            id="test_replan",
            name="test replan",
            original_trip=original,
            change_request="Change something",
            candidate_trip=updated,
            checks=checks,
            expected=expected,
        )

    def test_all_checks_pass(self):
        original = _trip("Paris", "2025-06-01", "2025-06-01", [])
        updated = _trip("Paris", "2025-06-01", "2025-06-01", [])
        case = self._make_case(original, updated, [destination_unchanged(), trip_dates_unchanged()])
        result = run_replanning_case(case)
        assert result.passed

    def test_category_is_replanning(self):
        original = _trip("Paris", "2025-06-01", "2025-06-01", [])
        case = self._make_case(original, original, [])
        result = run_replanning_case(case)
        assert result.category == "replanning"

    def test_expected_propagated_to_result(self):
        original = _trip("Paris", "2025-06-01", "2025-06-01", [])
        case = self._make_case(original, original, [], expected="fail")
        result = run_replanning_case(case)
        assert result.expected == "fail"


# ---------------------------------------------------------------------------
# AggregateReport tests
# ---------------------------------------------------------------------------


class TestAggregateReport:
    def _make_results(
        self,
        cases: list[tuple[str, bool, list[bool], str]],
    ) -> list[CaseResult]:
        """(case_id, passed, check_bools, expected)"""
        results = []
        for case_id, passed, check_results, expected in cases:
            checks = [
                CheckResult(name=f"check_{i}", passed=p) for i, p in enumerate(check_results)
            ]
            results.append(
                CaseResult(
                    case_id=case_id,
                    case_name=case_id,
                    category="planning",
                    passed=passed,
                    checks=checks,
                    expected=expected,
                )
            )
        return results

    def test_pass_rate_all_pass(self):
        results = self._make_results([
            ("c1", True, [True, True], "pass"),
            ("c2", True, [True], "pass"),
        ])
        report = build_report(results)
        assert report.case_pass_rate == 1.0
        assert report.check_pass_rate == 1.0

    def test_pass_rate_none_pass(self):
        results = self._make_results([
            ("c1", False, [False], "fail"),
            ("c2", False, [False, False], "fail"),
        ])
        report = build_report(results)
        assert report.case_pass_rate == 0.0
        assert report.check_pass_rate == 0.0

    def test_mixed_pass_rates(self):
        results = self._make_results([
            ("c1", True, [True, True], "pass"),
            ("c2", False, [False], "pass"),
        ])
        report = build_report(results)
        assert report.passed_cases == 1
        assert report.failed_cases == 1
        assert report.case_pass_rate == 0.5
        assert report.passed_checks == 2
        assert report.failed_checks == 1

    def test_planning_vs_replanning_counts(self):
        plan_result = CaseResult("p1", "p1", "planning", True, [], expected="pass")
        replan_result = CaseResult("r1", "r1", "replanning", False, [], expected="pass")
        report = build_report([plan_result, replan_result])
        assert report.planning_total == 1
        assert report.planning_passed == 1
        assert report.replanning_total == 1
        assert report.replanning_passed == 0

    def test_empty_report(self):
        report = build_report([])
        assert report.total_cases == 0
        assert report.case_pass_rate == 0.0
        assert report.check_pass_rate == 0.0

    def test_to_dict_is_json_serializable(self):
        import json

        results = self._make_results([("c1", True, [True], "pass")])
        report = build_report(results)
        d = report.to_dict()
        json.dumps(d)  # must not raise
        assert "case_results" in d
        assert d["total_cases"] == 1
        assert "expectation_met" in d
        assert "all_expectations_satisfied" in d

    def test_planning_pass_rate_zero_when_no_cases(self):
        report = build_report([])
        assert report.planning_pass_rate == 0.0
        assert report.replanning_pass_rate == 0.0

    # --- expectation tracking ---

    def test_expectation_met_positive_passes(self):
        results = self._make_results([("c1", True, [True], "pass")])
        report = build_report(results)
        assert report.expectation_met == 1
        assert report.expectation_unmet == 0
        assert report.all_expectations_satisfied

    def test_expectation_met_negative_fails(self):
        results = self._make_results([("c1", False, [False], "fail")])
        report = build_report(results)
        assert report.expectation_met == 1
        assert report.expectation_unmet == 0
        assert report.all_expectations_satisfied

    def test_expectation_unmet_positive_fails(self):
        # A positive fixture unexpectedly failed
        results = self._make_results([("c1", False, [False], "pass")])
        report = build_report(results)
        assert report.expectation_met == 0
        assert report.expectation_unmet == 1
        assert not report.all_expectations_satisfied

    def test_expectation_unmet_negative_passes(self):
        # A negative fixture unexpectedly passed (evaluator missed the bug)
        results = self._make_results([("c1", True, [True], "fail")])
        report = build_report(results)
        assert report.expectation_met == 0
        assert report.expectation_unmet == 1
        assert not report.all_expectations_satisfied

    def test_mixed_expectations(self):
        results = self._make_results([
            ("pos_ok", True, [True], "pass"),    # positive passes → expectation met
            ("neg_ok", False, [False], "fail"),  # negative fails → expectation met
            ("pos_bad", False, [False], "pass"),  # positive fails → expectation UNMET
        ])
        report = build_report(results)
        assert report.expectation_met == 2
        assert report.expectation_unmet == 1
        assert not report.all_expectations_satisfied


# ---------------------------------------------------------------------------
# Offline runner integration test
# ---------------------------------------------------------------------------


class TestRunOfflineEvals:
    def test_runs_all_fixture_cases(self):
        report = run_offline_evals()
        expected_total = len(ALL_PLANNING_CASES) + len(ALL_REPLANNING_CASES)
        assert report.total_cases == expected_total

    def test_positive_cases_all_pass(self):
        from app.evals.cases.planning import POSITIVE_CASES as PLAN_POS
        from app.evals.cases.replanning import POSITIVE_CASES as REPLAN_POS

        report = run_offline_evals(planning_cases=PLAN_POS, replanning_cases=REPLAN_POS)
        failed = [r for r in report.case_results if not r.passed]
        assert failed == [], f"Positive cases failed: {[r.case_id for r in failed]}"

    def test_negative_cases_all_fail(self):
        from app.evals.cases.planning import NEGATIVE_CASES as PLAN_NEG
        from app.evals.cases.replanning import NEGATIVE_CASES as REPLAN_NEG

        report = run_offline_evals(planning_cases=PLAN_NEG, replanning_cases=REPLAN_NEG)
        passed = [r for r in report.case_results if r.passed]
        assert passed == [], f"Negative cases unexpectedly passed: {[r.case_id for r in passed]}"

    def test_all_expectations_satisfied(self):
        """The full offline fixture suite should have all expectations met."""
        report = run_offline_evals()
        unmet = [r for r in report.case_results if not r.expectation_met]
        assert unmet == [], (
            f"Unexpected fixture outcomes: {[r.case_id for r in unmet]}"
        )
        assert report.all_expectations_satisfied

    def test_negative_cases_have_expected_fail(self):
        from app.evals.cases.planning import NEGATIVE_CASES as PLAN_NEG
        from app.evals.cases.replanning import NEGATIVE_CASES as REPLAN_NEG

        for case in list(PLAN_NEG) + list(REPLAN_NEG):
            assert case.expected == "fail", f"{case.id} should have expected='fail'"

    def test_positive_cases_have_expected_pass(self):
        from app.evals.cases.planning import POSITIVE_CASES as PLAN_POS
        from app.evals.cases.replanning import POSITIVE_CASES as REPLAN_POS

        for case in list(PLAN_POS) + list(REPLAN_POS):
            assert case.expected == "pass", f"{case.id} should have expected='pass'"

    def test_report_has_expected_planning_count(self):
        report = run_offline_evals()
        assert report.planning_total == len(ALL_PLANNING_CASES)
        assert report.replanning_total == len(ALL_REPLANNING_CASES)

    def test_case_ids_are_unique(self):
        report = run_offline_evals()
        ids = [r.case_id for r in report.case_results]
        assert len(ids) == len(set(ids))

    def test_expectation_rate_is_one(self):
        report = run_offline_evals()
        assert report.expectation_rate == 1.0


# ---------------------------------------------------------------------------
# Live case isolation test (no real API calls)
# ---------------------------------------------------------------------------


class TestLiveCases:
    def test_live_planning_cases_have_no_candidate(self):
        from app.evals.live_cases import LIVE_PLANNING_CASES

        for case in LIVE_PLANNING_CASES:
            assert case.candidate_trip is None, f"{case.id} should have candidate_trip=None"

    def test_live_replanning_cases_have_no_candidate(self):
        from app.evals.live_cases import LIVE_REPLANNING_CASES

        for case in LIVE_REPLANNING_CASES:
            assert case.candidate_trip is None, f"{case.id} should have candidate_trip=None"

    def test_live_planning_cases_have_checks(self):
        from app.evals.live_cases import LIVE_PLANNING_CASES

        for case in LIVE_PLANNING_CASES:
            assert len(case.checks) > 0, f"{case.id} has no checks"

    def test_live_replanning_cases_have_checks(self):
        from app.evals.live_cases import LIVE_REPLANNING_CASES

        for case in LIVE_REPLANNING_CASES:
            assert len(case.checks) > 0, f"{case.id} has no checks"
