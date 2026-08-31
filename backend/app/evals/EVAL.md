# Eval Framework

Deterministic evaluation harness for measuring planning and replanning reliability. All evaluations use predefined check functions — no LLM-as-judge.

## Modes

### Offline (fixture) evals — no API calls, fast, free

Runs 32 pre-built fixture cases (16 planning + 16 replanning). Each case includes a `candidate_trip` already built; the runner applies the check functions deterministically.

```
python -m app.evals.runner --offline
python -m app.evals.runner --offline --verbose     # show all check results
python -m app.evals.runner --offline --json        # machine-readable output
```

### Live evals — calls the real agent

Runs 5 live cases (3 planning + 2 replanning) against the real OpenAI + Google APIs. Requires `OPENAI_API_KEY` and `GOOGLE_API_KEY` in your `.env`.

```
python -m app.evals.runner --live                      # all 5 live cases
python -m app.evals.runner --live --type plan          # planning only
python -m app.evals.runner --live --type replan        # replanning only
python -m app.evals.runner --live --limit 2            # at most 2 cases
```

Estimated cost: ~$0.05–$0.15 per full live run (5 cases, gpt-4o).

## Exit code

- `0` — all cases passed
- `1` — one or more cases failed

## Architecture

```
app/evals/
├── models.py          # CheckResult, CaseResult, AggregateReport, PlanningEvalCase, ReplanEvalCase
├── checks.py          # Factory functions returning check closures
├── cases/
│   ├── planning.py    # 16 fixture planning cases (7 positive + 9 negative)
│   └── replanning.py  # 16 fixture replanning cases (8 positive + 8 negative)
├── live_cases.py      # 5 live cases (candidate_trip=None)
└── runner.py          # run_case, run_offline_evals, run_live_evals, build_report, CLI
```

## Check functions

### Planning checks (`Trip → CheckResult`)

| Function | What it verifies |
|---|---|
| `dates_match(request)` | `start_date` and `end_date` equal the request |
| `destination_preserved(request)` | Destination matches (case-insensitive) |
| `no_overlapping_activities()` | No two activities overlap on any day |
| `budget_respected(max_budget)` | Sum of all `estimated_cost` ≤ `max_budget` |
| `locked_activities_present(locked)` | All locked activities appear by name |
| `all_days_represented(request)` | Every date in the range has a `TripDay` |
| `has_activities()` | At least one activity exists in the trip |

### Replanning checks (`(original: Trip, updated: Trip) → CheckResult`)

| Function | What it verifies |
|---|---|
| `locked_preserved_after_replan(original)` | Locked activities unchanged (name + times) |
| `unaffected_days_unchanged(excluded_dates)` | Days not in excluded_dates have the same activity names |
| `affected_date_changed(expected_date)` | The specified date has different activities |
| `no_overlaps_after_replan()` | No overlaps in the updated trip |
| `budget_maintained(max_budget)` | Updated trip total ≤ `max_budget` |
| `destination_unchanged()` | Destination not modified |
| `trip_dates_unchanged()` | `start_date` and `end_date` not modified |

## Adding cases

Add to `app/evals/cases/planning.py` or `app/evals/cases/replanning.py`. Positive cases should use checks that the fixture trip satisfies; negative cases should have exactly the checks that the fixture trip violates.

```python
PlanningEvalCase(
    id="plan_pos_99",
    name="my new case",
    request=_req("Paris", "2025-06-01", "2025-06-01"),
    candidate_trip=_trip(...),
    checks=[dates_match(...), no_overlapping_activities()],
)
```

Set `candidate_trip=None` to make a live case that calls the real agent.
