"""Core planning / replanning orchestration.

Control flow
------------
plan_trip
  └─ _run_agent_loop          (tool-calling loop, max MAX_AGENT_ITERATIONS)
  └─ _parse_and_repair        (JSON → Trip, max MAX_PARSE_RETRIES)
  └─ _validate_and_repair     (deterministic validator, max MAX_REPAIR_RETRIES)

replan_trip
  └─ (same three stages, but with an existing trip in context)
  └─ _compute_change_summary  (structured diff of original vs updated)
"""

import json
import logging

from openai import AsyncOpenAI

from ..config import settings
from ..models.trip import Trip
from ..validation.itinerary import validate_itinerary
from .exceptions import MaxIterationsError, PlanningError, ValidationFailedError
from .models import AgentRunMetadata, ReplanResult, TripChangeSummary, TripPlanRequest
from .prompts import (
    SYSTEM_PROMPT,
    build_parse_repair_prompt,
    build_planning_prompt,
    build_replan_prompt,
    build_validation_repair_prompt,
)
from .tools import TOOL_DEFINITIONS, execute_tool

logger = logging.getLogger(__name__)

MAX_AGENT_ITERATIONS = 15
MAX_PARSE_RETRIES = 3
MAX_REPAIR_RETRIES = 2


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def plan_trip(
    request: TripPlanRequest,
    *,
    _client: AsyncOpenAI | None = None,
) -> tuple[Trip, AgentRunMetadata]:
    """Generate a new structured itinerary from a TripPlanRequest.

    Returns (Trip, AgentRunMetadata).  Raises PlanningError / subclasses on
    failure.
    """
    client = _client or AsyncOpenAI(api_key=settings.openai_api_key)
    metadata = AgentRunMetadata()

    try:
        raw_json = await _run_agent_loop(
            client, build_planning_prompt(request), metadata
        )
        trip = await _parse_and_repair(client, raw_json, metadata)
        trip = await _validate_and_repair(
            client, trip, original_trip=None, metadata=metadata
        )
        metadata.success = True
        return trip, metadata
    except PlanningError:
        raise
    except Exception as exc:
        metadata.error = str(exc)
        raise PlanningError(f"Unexpected error during planning: {exc}") from exc


async def replan_trip(
    existing_trip: Trip,
    change_request: str,
    *,
    _client: AsyncOpenAI | None = None,
) -> ReplanResult:
    """Replan an existing trip given a natural-language change request.

    Locked activities are preserved.  The result includes a structured
    change summary.
    """
    client = _client or AsyncOpenAI(api_key=settings.openai_api_key)
    metadata = AgentRunMetadata()

    locked_names = [
        act.name
        for day in existing_trip.days
        for act in day.activities
        if act.locked
    ]
    existing_json = existing_trip.model_dump_json(indent=2)
    prompt = build_replan_prompt(existing_json, change_request, locked_names)

    try:
        raw_json = await _run_agent_loop(client, prompt, metadata)
        new_trip = await _parse_and_repair(client, raw_json, metadata)
        new_trip = await _validate_and_repair(
            client, new_trip, original_trip=existing_trip, metadata=metadata
        )
        summary = _compute_change_summary(existing_trip, new_trip)
        return ReplanResult(trip=new_trip, change_summary=summary)
    except PlanningError:
        raise
    except Exception as exc:
        metadata.error = str(exc)
        raise PlanningError(f"Unexpected error during replanning: {exc}") from exc


# ---------------------------------------------------------------------------
# Agent loop
# ---------------------------------------------------------------------------


async def _run_agent_loop(
    client: AsyncOpenAI,
    user_prompt: str,
    metadata: AgentRunMetadata,
) -> str:
    """Drive the Responses API tool-calling loop.

    Sends the user prompt, executes any tool calls the model requests, and
    returns the model's final text response (expected to be Trip JSON).

    Raises MaxIterationsError if MAX_AGENT_ITERATIONS is exhausted.
    Raises PlanningError on API failures or unexpected empty output.
    """
    # Build the conversation input list manually so the flow is explicit and
    # easily testable without server-side state.
    conversation: list = [{"role": "user", "content": user_prompt}]

    for iteration in range(MAX_AGENT_ITERATIONS):
        try:
            response = await client.responses.create(
                model=settings.openai_model,
                instructions=SYSTEM_PROMPT,
                input=conversation,
                tools=TOOL_DEFINITIONS,
            )
        except Exception as exc:
            raise PlanningError(f"OpenAI API error: {exc}") from exc

        tool_calls = [
            item for item in response.output if item.type == "function_call"
        ]
        messages = [item for item in response.output if item.type == "message"]

        if messages:
            msg = messages[0]
            return "".join(
                part.text for part in msg.content if part.type == "output_text"
            )

        if not tool_calls:
            raise PlanningError(
                f"Agent produced no output on iteration {iteration + 1} "
                "(neither tool calls nor a message)"
            )

        # Add the model's function-call items to the conversation so the next
        # API call has the full history.
        for tc in tool_calls:
            conversation.append(tc.model_dump(exclude_none=True))

        # Execute each tool and append its result.
        for tc in tool_calls:
            metadata.tools_called.append(tc.name)
            metadata.tool_call_count += 1
            result = await execute_tool(tc.name, tc.arguments)
            conversation.append(
                {
                    "type": "function_call_output",
                    "call_id": tc.call_id,
                    "output": result,
                }
            )

    raise MaxIterationsError(
        f"Agent did not produce a final response within "
        f"{MAX_AGENT_ITERATIONS} iterations"
    )


# ---------------------------------------------------------------------------
# Parse + repair
# ---------------------------------------------------------------------------


def _strip_fences(text: str) -> str:
    """Remove markdown code fences that models occasionally add."""
    text = text.strip()
    if text.startswith("```"):
        # Drop the opening fence line (```json or ```)
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1 :]
        # Drop a trailing fence
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
        text = text.strip()
    return text


async def _parse_and_repair(
    client: AsyncOpenAI,
    raw_json: str,
    metadata: AgentRunMetadata,
) -> Trip:
    """Parse raw JSON text as a Trip, with bounded repair retries.

    On each failure the model is given the error and asked to fix its output.
    Raises PlanningError after MAX_PARSE_RETRIES exhausted.
    """
    current_json = raw_json

    for attempt in range(MAX_PARSE_RETRIES):
        try:
            data = json.loads(_strip_fences(current_json))
            return Trip(**data)
        except Exception as exc:
            error_str = str(exc)
            metadata.validation_attempts += 1
            metadata.validation_failures.append(f"parse:{error_str}")
            logger.debug("Trip parse attempt %d failed: %s", attempt + 1, error_str)

            if attempt == MAX_PARSE_RETRIES - 1:
                raise PlanningError(
                    f"Could not produce a valid Trip after {MAX_PARSE_RETRIES} "
                    f"parse attempts. Last error: {error_str}"
                )

            # Ask the model to fix its output.
            try:
                fix_resp = await client.responses.create(
                    model=settings.openai_model,
                    instructions=SYSTEM_PROMPT,
                    input=[
                        {
                            "role": "user",
                            "content": build_parse_repair_prompt(
                                current_json, error_str
                            ),
                        }
                    ],
                )
            except Exception as api_exc:
                raise PlanningError(
                    f"OpenAI API error during parse repair: {api_exc}"
                ) from api_exc

            current_json = _extract_text(fix_resp)

    # Unreachable — loop always raises or returns first.
    raise PlanningError("Parse-and-repair loop exited unexpectedly")  # pragma: no cover


# ---------------------------------------------------------------------------
# Validate + repair
# ---------------------------------------------------------------------------


async def _validate_and_repair(
    client: AsyncOpenAI,
    trip: Trip,
    original_trip: Trip | None,
    metadata: AgentRunMetadata,
) -> Trip:
    """Run the deterministic validator with bounded repair retries.

    On each validation failure the model receives the structured error list and
    a copy of the current trip JSON, then produces a corrected version.
    Raises ValidationFailedError after MAX_REPAIR_RETRIES exhausted.
    """
    current_trip = trip

    for attempt in range(MAX_REPAIR_RETRIES + 1):
        result = await validate_itinerary(current_trip, original_trip=original_trip)
        metadata.validation_attempts += 1

        if result.valid:
            return current_trip

        errors = [issue.message for issue in result.errors]
        metadata.validation_failures.extend(errors)
        logger.debug(
            "Validation attempt %d found %d error(s): %s",
            attempt + 1,
            len(errors),
            errors,
        )

        if attempt == MAX_REPAIR_RETRIES:
            break  # Give up after the last allowed repair.

        trip_json = current_trip.model_dump_json(indent=2)
        try:
            fix_resp = await client.responses.create(
                model=settings.openai_model,
                instructions=SYSTEM_PROMPT,
                input=[
                    {
                        "role": "user",
                        "content": build_validation_repair_prompt(trip_json, errors),
                    }
                ],
            )
        except Exception as api_exc:
            raise PlanningError(
                f"OpenAI API error during validation repair: {api_exc}"
            ) from api_exc

        try:
            current_trip = Trip(**json.loads(_strip_fences(_extract_text(fix_resp))))
        except Exception as exc:
            metadata.validation_failures.append(f"repair_parse:{exc}")
            logger.debug("Repair parse failed on attempt %d: %s", attempt + 1, exc)
            break

    raise ValidationFailedError(
        f"Itinerary validation failed after {MAX_REPAIR_RETRIES} repair attempt(s)",
        failures=metadata.validation_failures,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_text(response) -> str:  # type: ignore[return]
    """Extract the text content from a Responses API response object."""
    for item in response.output:
        if item.type == "message":
            return "".join(
                part.text for part in item.content if part.type == "output_text"
            )
    raise PlanningError("Response contained no message output")


def _compute_change_summary(original: Trip, updated: Trip) -> TripChangeSummary:
    """Produce a structured diff of what changed between two trips."""
    from datetime import date as _date

    orig_by_day: dict[_date, dict[str, object]] = {
        day.date: {act.name: act for act in day.activities}
        for day in original.days
    }
    new_by_day: dict[_date, dict[str, object]] = {
        day.date: {act.name: act for act in day.activities}
        for day in updated.days
    }

    all_dates = sorted(set(orig_by_day) | set(new_by_day))
    added = removed = changed = locked_changed = 0
    affected: list[_date] = []

    for d in all_dates:
        orig_acts = orig_by_day.get(d, {})
        new_acts = new_by_day.get(d, {})
        day_touched = False

        for name in set(orig_acts) - set(new_acts):
            removed += 1
            day_touched = True
            if orig_acts[name].locked:  # type: ignore[attr-defined]
                locked_changed += 1

        for name in set(new_acts) - set(orig_acts):
            added += 1
            day_touched = True

        for name in set(orig_acts) & set(new_acts):
            o = orig_acts[name]  # type: ignore[assignment]
            n = new_acts[name]  # type: ignore[assignment]
            if (
                o.start_time != n.start_time  # type: ignore[attr-defined]
                or o.end_time != n.end_time  # type: ignore[attr-defined]
                or o.location != n.location  # type: ignore[attr-defined]
            ):
                changed += 1
                day_touched = True
                if o.locked:  # type: ignore[attr-defined]
                    locked_changed += 1

        if day_touched:
            affected.append(d)

    orig_cost = sum(
        float(a.estimated_cost) for day in original.days for a in day.activities
    )
    new_cost = sum(
        float(a.estimated_cost) for day in updated.days for a in day.activities
    )

    parts: list[str] = []
    if added:
        parts.append(f"{added} added")
    if removed:
        parts.append(f"{removed} removed")
    if changed:
        parts.append(f"{changed} modified")

    return TripChangeSummary(
        activities_added=added,
        activities_removed=removed,
        activities_changed=changed,
        affected_dates=affected,
        budget_difference=round(new_cost - orig_cost, 2),
        locked_activities_changed=locked_changed,
        summary="; ".join(parts) if parts else "No changes",
    )
