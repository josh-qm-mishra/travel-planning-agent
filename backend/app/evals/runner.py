"""Eval runner — offline fixture evals and live agent evals.

Usage:
    python -m app.evals.runner --offline
    python -m app.evals.runner --live --limit 3
    python -m app.evals.runner --live --type plan --limit 2
    python -m app.evals.runner --live --type replan --limit 2
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Sequence

from .cases import ALL_PLANNING_CASES, ALL_REPLANNING_CASES
from .live_cases import LIVE_PLANNING_CASES, LIVE_REPLANNING_CASES
from .models import (
    AggregateReport,
    CaseResult,
    CheckResult,
    PlanningEvalCase,
    ReplanEvalCase,
)


# ---------------------------------------------------------------------------
# Individual case runners
# ---------------------------------------------------------------------------


def run_planning_case(case: PlanningEvalCase) -> CaseResult:
    """Run a single planning eval case (fixture only — no live calls)."""
    assert case.candidate_trip is not None, "Use run_planning_case_live for live cases"
    checks: list[CheckResult] = []
    try:
        for fn in case.checks:
            checks.append(fn(case.candidate_trip))
    except Exception as exc:
        return CaseResult(
            case_id=case.id,
            case_name=case.name,
            category="planning",
            passed=False,
            checks=checks,
            expected=case.expected,
            error=f"Check raised exception: {exc}",
        )
    passed = all(c.passed for c in checks)
    return CaseResult(
        case_id=case.id,
        case_name=case.name,
        category="planning",
        passed=passed,
        checks=checks,
        expected=case.expected,
    )


def run_replanning_case(case: ReplanEvalCase) -> CaseResult:
    """Run a single replanning eval case (fixture only — no live calls)."""
    assert case.candidate_trip is not None, "Use run_replanning_case_live for live cases"
    checks: list[CheckResult] = []
    try:
        for fn in case.checks:
            checks.append(fn(case.original_trip, case.candidate_trip))
    except Exception as exc:
        return CaseResult(
            case_id=case.id,
            case_name=case.name,
            category="replanning",
            passed=False,
            checks=checks,
            expected=case.expected,
            error=f"Check raised exception: {exc}",
        )
    passed = all(c.passed for c in checks)
    return CaseResult(
        case_id=case.id,
        case_name=case.name,
        category="replanning",
        passed=passed,
        checks=checks,
        expected=case.expected,
    )


async def run_planning_case_live(case: PlanningEvalCase) -> CaseResult:
    """Run a planning case by invoking the real agent."""
    from ..agent.exceptions import PlanningError
    from ..agent.planner import plan_trip

    checks: list[CheckResult] = []
    try:
        trip, _ = await plan_trip(case.request)
        for fn in case.checks:
            checks.append(fn(trip))
    except PlanningError as exc:
        return CaseResult(
            case_id=case.id,
            case_name=case.name,
            category="planning",
            passed=False,
            checks=checks,
            expected=case.expected,
            error=f"PlanningError: {exc}",
        )
    except Exception as exc:
        return CaseResult(
            case_id=case.id,
            case_name=case.name,
            category="planning",
            passed=False,
            checks=checks,
            expected=case.expected,
            error=f"Unexpected error: {exc}",
        )
    passed = all(c.passed for c in checks)
    return CaseResult(
        case_id=case.id,
        case_name=case.name,
        category="planning",
        passed=passed,
        checks=checks,
        expected=case.expected,
    )


async def run_replanning_case_live(case: ReplanEvalCase) -> CaseResult:
    """Run a replanning case by invoking the real agent."""
    from ..agent.exceptions import PlanningError
    from ..agent.planner import replan_trip

    checks: list[CheckResult] = []
    try:
        result = await replan_trip(case.original_trip, case.change_request)
        for fn in case.checks:
            checks.append(fn(case.original_trip, result.trip))
    except PlanningError as exc:
        return CaseResult(
            case_id=case.id,
            case_name=case.name,
            category="replanning",
            passed=False,
            checks=checks,
            expected=case.expected,
            error=f"PlanningError: {exc}",
        )
    except Exception as exc:
        return CaseResult(
            case_id=case.id,
            case_name=case.name,
            category="replanning",
            passed=False,
            checks=checks,
            expected=case.expected,
            error=f"Unexpected error: {exc}",
        )
    passed = all(c.passed for c in checks)
    return CaseResult(
        case_id=case.id,
        case_name=case.name,
        category="replanning",
        passed=passed,
        checks=checks,
        expected=case.expected,
    )


# ---------------------------------------------------------------------------
# Batch runners
# ---------------------------------------------------------------------------


def run_offline_evals(
    planning_cases: Sequence[PlanningEvalCase] | None = None,
    replanning_cases: Sequence[ReplanEvalCase] | None = None,
) -> AggregateReport:
    """Run all offline (fixture) eval cases synchronously."""
    if planning_cases is None:
        planning_cases = ALL_PLANNING_CASES
    if replanning_cases is None:
        replanning_cases = ALL_REPLANNING_CASES

    results: list[CaseResult] = []
    for case in planning_cases:
        results.append(run_planning_case(case))
    for case in replanning_cases:
        results.append(run_replanning_case(case))

    return build_report(results)


async def run_live_evals(
    include_planning: bool = True,
    include_replanning: bool = True,
    limit: int | None = None,
) -> AggregateReport:
    """Run live eval cases against the real agent (requires API keys)."""
    cases: list[PlanningEvalCase | ReplanEvalCase] = []
    if include_planning:
        cases.extend(LIVE_PLANNING_CASES)
    if include_replanning:
        cases.extend(LIVE_REPLANNING_CASES)

    if limit is not None:
        cases = cases[:limit]

    results: list[CaseResult] = []
    for case in cases:
        if isinstance(case, PlanningEvalCase):
            results.append(await run_planning_case_live(case))
        else:
            results.append(await run_replanning_case_live(case))

    return build_report(results)


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------


def build_report(results: list[CaseResult]) -> AggregateReport:
    planning_results = [r for r in results if r.category == "planning"]
    replanning_results = [r for r in results if r.category == "replanning"]

    all_checks = [c for r in results for c in r.checks]

    return AggregateReport(
        total_cases=len(results),
        passed_cases=sum(1 for r in results if r.passed),
        failed_cases=sum(1 for r in results if not r.passed),
        expectation_met=sum(1 for r in results if r.expectation_met),
        expectation_unmet=sum(1 for r in results if not r.expectation_met),
        total_checks=len(all_checks),
        passed_checks=sum(1 for c in all_checks if c.passed),
        failed_checks=sum(1 for c in all_checks if not c.passed),
        planning_total=len(planning_results),
        planning_passed=sum(1 for r in planning_results if r.passed),
        replanning_total=len(replanning_results),
        replanning_passed=sum(1 for r in replanning_results if r.passed),
        case_results=results,
    )


# ---------------------------------------------------------------------------
# CLI pretty-printer
# ---------------------------------------------------------------------------


def _print_report(report: AggregateReport, verbose: bool = False, is_offline: bool = False) -> None:
    print()
    print("=" * 60)
    print("EVAL RESULTS")
    print("=" * 60)

    if is_offline:
        # Lead with expectation-match rate for offline runs
        print(
            f"Expectations: {report.expectation_met}/{report.total_cases} matched "
            f"({report.expectation_rate:.0%})"
        )
        if report.expectation_unmet:
            print(f"  WARNING: {report.expectation_unmet} case(s) behaved unexpectedly")
        print()
        print("Raw candidate outcomes (positive/negative fixture breakdown):")
        pos = sum(1 for r in report.case_results if r.expected == "pass")
        pos_pass = sum(1 for r in report.case_results if r.expected == "pass" and r.passed)
        neg = sum(1 for r in report.case_results if r.expected == "fail")
        neg_fail = sum(1 for r in report.case_results if r.expected == "fail" and not r.passed)
        print(f"  Positive fixtures (expected pass): {pos_pass}/{pos} passed checks")
        print(f"  Negative fixtures (expected fail): {neg_fail}/{neg} correctly failed checks")
        print(f"Checks: {report.passed_checks}/{report.total_checks} passed overall")
    else:
        # Live mode: candidate outcomes ARE the reliability signal
        print(
            f"Cases:  {report.passed_cases}/{report.total_cases} passed "
            f"({report.case_pass_rate:.0%})"
        )
        print(
            f"Checks: {report.passed_checks}/{report.total_checks} passed "
            f"({report.check_pass_rate:.0%})"
        )

    if report.planning_total:
        print(
            f"  Planning:   {report.planning_passed}/{report.planning_total} "
            f"({report.planning_pass_rate:.0%})"
        )
    if report.replanning_total:
        print(
            f"  Replanning: {report.replanning_passed}/{report.replanning_total} "
            f"({report.replanning_pass_rate:.0%})"
        )
    print()

    for result in report.case_results:
        if is_offline:
            # For offline runs show expectation-match as the top-level status
            if result.expectation_met:
                status = "OK  "
                label = f"[expected {result.expected.upper()}]"
            else:
                status = "UNEXPECTED"
                label = f"[expected {result.expected.upper()}, got {'PASS' if result.passed else 'FAIL'}]"
        else:
            status = "PASS" if result.passed else "FAIL"
            label = ""

        line = f"  [{status}] {result.case_id}: {result.case_name}"
        if label:
            line += f"  {label}"
        print(line)

        show_detail = not result.expectation_met if is_offline else not result.passed
        if show_detail or verbose:
            if result.error:
                print(f"         error: {result.error}")
            for check in result.checks:
                check_status = "ok" if check.passed else "FAIL"
                msg = f"  {check.name}: {check_status}"
                if not check.passed and check.reason:
                    msg += f" — {check.reason}"
                print(f"         {msg}")

    print()


def _check_live_credentials() -> None:
    from ..config import settings

    missing = []
    if not settings.openai_api_key:
        missing.append("OPENAI_API_KEY")
    if not settings.google_api_key:
        missing.append("GOOGLE_API_KEY")
    if missing:
        print(f"ERROR: Missing required environment variables: {', '.join(missing)}")
        print("Set them in your .env file or as environment variables before running live evals.")
        sys.exit(1)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Travel planning agent eval runner")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--offline", action="store_true", help="Run offline fixture evals")
    mode.add_argument("--live", action="store_true", help="Run live agent evals (requires API keys)")
    parser.add_argument(
        "--type",
        choices=["plan", "replan", "all"],
        default="all",
        help="Which live case type to run (default: all)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max number of live cases to run",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show all check results, not just failures",
    )
    args = parser.parse_args(argv)

    if args.offline:
        report = run_offline_evals()
        if args.json:
            print(json.dumps(report.to_dict(), indent=2))
        else:
            _print_report(report, verbose=args.verbose, is_offline=True)
        # Offline: exit 0 iff all fixture expectations are satisfied
        sys.exit(0 if report.all_expectations_satisfied else 1)
    else:
        _check_live_credentials()
        include_planning = args.type in ("plan", "all")
        include_replanning = args.type in ("replan", "all")
        report = asyncio.run(
            run_live_evals(
                include_planning=include_planning,
                include_replanning=include_replanning,
                limit=args.limit,
            )
        )
        if args.json:
            print(json.dumps(report.to_dict(), indent=2))
        else:
            _print_report(report, verbose=args.verbose, is_offline=False)
        # Live: exit 0 iff all candidate outputs satisfy their checks
        sys.exit(0 if report.passed_cases == report.total_cases else 1)


if __name__ == "__main__":
    main()
