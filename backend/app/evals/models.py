"""Eval framework data models."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Literal

from ..agent.models import TripPlanRequest
from ..models.trip import Trip

# ---------------------------------------------------------------------------
# Check function type aliases
# ---------------------------------------------------------------------------

PlanCheckFn = Callable[[Trip], "CheckResult"]
ReplanCheckFn = Callable[[Trip, Trip], "CheckResult"]  # (original, updated)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class CheckResult:
    name: str
    passed: bool
    reason: str = ""


@dataclass
class CaseResult:
    case_id: str
    case_name: str
    category: str  # "planning" | "replanning"
    passed: bool            # True if all checks passed
    checks: list[CheckResult]
    expected: str = "pass"  # declared expectation: "pass" | "fail"
    error: str = ""

    @property
    def expectation_met(self) -> bool:
        """True when the actual outcome (passed/failed) matches declared expectation."""
        if self.expected == "pass":
            return self.passed
        return not self.passed  # expected="fail": expectation met when checks failed


@dataclass
class AggregateReport:
    total_cases: int
    passed_cases: int       # candidates that satisfied all checks
    failed_cases: int       # candidates that violated at least one check
    expectation_met: int    # cases where actual == expected
    expectation_unmet: int  # cases where actual != expected (genuine surprises)
    total_checks: int
    passed_checks: int
    failed_checks: int
    planning_total: int
    planning_passed: int
    replanning_total: int
    replanning_passed: int
    case_results: list[CaseResult]

    # --- raw candidate metrics ---

    @property
    def case_pass_rate(self) -> float:
        return self.passed_cases / self.total_cases if self.total_cases else 0.0

    @property
    def check_pass_rate(self) -> float:
        return self.passed_checks / self.total_checks if self.total_checks else 0.0

    @property
    def planning_pass_rate(self) -> float:
        return self.planning_passed / self.planning_total if self.planning_total else 0.0

    @property
    def replanning_pass_rate(self) -> float:
        return self.replanning_passed / self.replanning_total if self.replanning_total else 0.0

    # --- expectation metrics ---

    @property
    def expectation_rate(self) -> float:
        return self.expectation_met / self.total_cases if self.total_cases else 0.0

    @property
    def all_expectations_satisfied(self) -> bool:
        return self.expectation_unmet == 0

    def to_dict(self) -> dict:
        return {
            # expectation-level summary
            "expectation_met": self.expectation_met,
            "expectation_unmet": self.expectation_unmet,
            "expectation_rate": round(self.expectation_rate, 4),
            "all_expectations_satisfied": self.all_expectations_satisfied,
            # raw candidate metrics
            "total_cases": self.total_cases,
            "passed_cases": self.passed_cases,
            "failed_cases": self.failed_cases,
            "case_pass_rate": round(self.case_pass_rate, 4),
            "total_checks": self.total_checks,
            "passed_checks": self.passed_checks,
            "failed_checks": self.failed_checks,
            "check_pass_rate": round(self.check_pass_rate, 4),
            "planning_total": self.planning_total,
            "planning_passed": self.planning_passed,
            "planning_pass_rate": round(self.planning_pass_rate, 4),
            "replanning_total": self.replanning_total,
            "replanning_passed": self.replanning_passed,
            "replanning_pass_rate": round(self.replanning_pass_rate, 4),
            "case_results": [
                {
                    "id": r.case_id,
                    "name": r.case_name,
                    "category": r.category,
                    "expected": r.expected,
                    "passed": r.passed,
                    "expectation_met": r.expectation_met,
                    "error": r.error,
                    "checks": [
                        {"name": c.name, "passed": c.passed, "reason": c.reason}
                        for c in r.checks
                    ],
                }
                for r in self.case_results
            ],
        }


# ---------------------------------------------------------------------------
# Eval case types
# ---------------------------------------------------------------------------


@dataclass
class PlanningEvalCase:
    id: str
    name: str
    request: TripPlanRequest
    checks: list[PlanCheckFn]
    candidate_trip: Trip | None = None  # None → live (calls plan_trip)
    expected: Literal["pass", "fail"] = "pass"


@dataclass
class ReplanEvalCase:
    id: str
    name: str
    original_trip: Trip
    change_request: str
    checks: list[ReplanCheckFn]
    candidate_trip: Trip | None = None  # None → live (calls replan_trip)
    expected: Literal["pass", "fail"] = "pass"
