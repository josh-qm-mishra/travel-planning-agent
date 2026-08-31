"""Tests for the AI planning agent (planner.py).

All OpenAI API calls are mocked — no live network calls are made.
"""
import json
import pytest
from datetime import date, time
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from openai.types.responses import (
    Response,
    ResponseFunctionToolCall,
    ResponseOutputMessage,
    ResponseOutputText,
)

from app.agent.exceptions import MaxIterationsError, PlanningError, ValidationFailedError
from app.agent.models import AgentRunMetadata, ReplanResult, TripChangeSummary, TripPlanRequest
from app.agent.planner import (
    MAX_AGENT_ITERATIONS,
    _compute_change_summary,
    _strip_fences,
    plan_trip,
    replan_trip,
)
from app.models.trip import Activity, Trip, TripConstraints, TripDay, TripPreferences


# ---------------------------------------------------------------------------
# Minimal Trip JSON fixture (valid, parseable, passes validator)
# ---------------------------------------------------------------------------

VALID_TRIP_JSON = json.dumps(
    {
        "destination": "Paris",
        "start_date": "2025-06-01",
        "end_date": "2025-06-01",
        "total_budget": None,
        "preferences": {
            "interests": [],
            "food_preferences": [],
            "pace": "moderate",
            "morning_preference": True,
            "walking_tolerance": "moderate",
        },
        "constraints": {
            "earliest_start_time": None,
            "latest_end_time": None,
            "maximum_budget": None,
        },
        "days": [
            {
                "date": "2025-06-01",
                "activities": [
                    {
                        "name": "Eiffel Tower",
                        "location": "Champ de Mars, Paris",
                        "start_time": "09:00:00",
                        "end_time": "11:00:00",
                        "estimated_cost": 25.0,
                        "category": "sightseeing",
                        "locked": False,
                        "notes": None,
                    },
                    {
                        "name": "Lunch at Café",
                        "location": "Rue de Rivoli, Paris",
                        "start_time": "12:00:00",
                        "end_time": "13:00:00",
                        "estimated_cost": 20.0,
                        "category": "food",
                        "locked": False,
                        "notes": None,
                    },
                ],
            }
        ],
    }
)


def _make_trip_from_json(json_str: str = VALID_TRIP_JSON) -> Trip:
    return Trip(**json.loads(json_str))


# ---------------------------------------------------------------------------
# Mock response builders
# ---------------------------------------------------------------------------


def _text_response(text: str) -> MagicMock:
    """Build a mock Response that contains a single text message."""
    msg = ResponseOutputMessage(
        id="msg_1",
        content=[ResponseOutputText(text=text, type="output_text", annotations=[])],
        role="assistant",
        status="completed",
        type="message",
    )
    resp = MagicMock()
    resp.output = [msg]
    return resp


def _tool_call_response(name: str, arguments: dict, call_id: str = "call_1") -> MagicMock:
    """Build a mock Response that contains a single function tool call."""
    tc = ResponseFunctionToolCall(
        arguments=json.dumps(arguments),
        call_id=call_id,
        name=name,
        type="function_call",
        id="fc_1",
        status="completed",
    )
    resp = MagicMock()
    resp.output = [tc]
    return resp


def _empty_response() -> MagicMock:
    resp = MagicMock()
    resp.output = []
    return resp


# ---------------------------------------------------------------------------
# _strip_fences
# ---------------------------------------------------------------------------


def test_strip_fences_plain_json():
    raw = '{"key": "value"}'
    assert _strip_fences(raw) == raw


def test_strip_fences_removes_json_fence():
    raw = "```json\n{\"key\": \"value\"}\n```"
    assert _strip_fences(raw) == '{"key": "value"}'


def test_strip_fences_removes_plain_fence():
    raw = "```\n{\"key\": \"value\"}\n```"
    assert _strip_fences(raw) == '{"key": "value"}'


def test_strip_fences_handles_no_trailing_fence():
    raw = "```json\n{\"key\": \"value\"}"
    # No trailing fence → strip opening line only
    result = _strip_fences(raw)
    assert "```" not in result


# ---------------------------------------------------------------------------
# plan_trip — happy path
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_plan_trip_single_shot():
    """Agent returns Trip JSON in a single response."""
    mock_client = AsyncMock()
    mock_client.responses.create = AsyncMock(return_value=_text_response(VALID_TRIP_JSON))

    trip, metadata = await plan_trip(
        TripPlanRequest(
            destination="Paris",
            start_date=date(2025, 6, 1),
            end_date=date(2025, 6, 1),
        ),
        _client=mock_client,
    )

    assert isinstance(trip, Trip)
    assert trip.destination == "Paris"
    assert metadata.success is True
    assert mock_client.responses.create.call_count == 1


@pytest.mark.anyio
async def test_plan_trip_with_tool_call_then_json():
    """Agent makes one tool call, then returns Trip JSON."""
    from app.tools.models import GeocodingLocation

    geo_result = GeocodingLocation(
        name="Paris", latitude=48.8566, longitude=2.3522, country="France", admin1=None
    )

    tool_resp = _tool_call_response("geocode_location", {"query": "Paris, France"})
    text_resp = _text_response(VALID_TRIP_JSON)

    mock_client = AsyncMock()
    mock_client.responses.create = AsyncMock(side_effect=[tool_resp, text_resp])

    with patch(
        "app.agent.tools.geocode_location",
        return_value=geo_result,
    ):
        trip, metadata = await plan_trip(
            TripPlanRequest(
                destination="Paris",
                start_date=date(2025, 6, 1),
                end_date=date(2025, 6, 1),
            ),
            _client=mock_client,
        )

    assert isinstance(trip, Trip)
    assert metadata.tool_call_count == 1
    assert "geocode_location" in metadata.tools_called
    assert metadata.success is True


@pytest.mark.anyio
async def test_plan_trip_with_fenced_json():
    """Agent wraps JSON in markdown fences — should still parse successfully."""
    fenced = "```json\n" + VALID_TRIP_JSON + "\n```"
    mock_client = AsyncMock()
    mock_client.responses.create = AsyncMock(return_value=_text_response(fenced))

    trip, metadata = await plan_trip(
        TripPlanRequest(
            destination="Paris",
            start_date=date(2025, 6, 1),
            end_date=date(2025, 6, 1),
        ),
        _client=mock_client,
    )

    assert isinstance(trip, Trip)
    assert metadata.success is True


# ---------------------------------------------------------------------------
# plan_trip — parse repair
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_plan_trip_repairs_bad_json():
    """First response is invalid JSON; second (repair) response is valid."""
    bad_json = "this is not json"
    mock_client = AsyncMock()
    mock_client.responses.create = AsyncMock(
        side_effect=[
            _text_response(bad_json),      # initial: bad JSON
            _text_response(VALID_TRIP_JSON),  # repair: valid
        ]
    )

    trip, metadata = await plan_trip(
        TripPlanRequest(
            destination="Paris",
            start_date=date(2025, 6, 1),
            end_date=date(2025, 6, 1),
        ),
        _client=mock_client,
    )

    assert isinstance(trip, Trip)
    assert metadata.validation_attempts >= 1
    assert len(metadata.validation_failures) >= 1


@pytest.mark.anyio
async def test_plan_trip_raises_after_exhausting_parse_retries():
    """All parse repair attempts fail → PlanningError raised."""
    mock_client = AsyncMock()
    mock_client.responses.create = AsyncMock(
        return_value=_text_response("not json at all")
    )

    with pytest.raises(PlanningError, match="parse"):
        await plan_trip(
            TripPlanRequest(
                destination="Paris",
                start_date=date(2025, 6, 1),
                end_date=date(2025, 6, 1),
            ),
            _client=mock_client,
        )


# ---------------------------------------------------------------------------
# plan_trip — validation repair
# ---------------------------------------------------------------------------


def _overlapping_trip_json() -> str:
    """Trip JSON with an overlap error (activities overlap)."""
    data = json.loads(VALID_TRIP_JSON)
    # Make activities overlap
    data["days"][0]["activities"][1]["start_time"] = "10:00:00"
    return json.dumps(data)


@pytest.mark.anyio
async def test_plan_trip_repairs_validation_error():
    """First trip has overlap; repair response returns valid trip."""
    bad = _overlapping_trip_json()
    mock_client = AsyncMock()
    mock_client.responses.create = AsyncMock(
        side_effect=[
            _text_response(bad),           # initial: schedule overlap
            _text_response(VALID_TRIP_JSON),  # repair: valid
        ]
    )

    trip, metadata = await plan_trip(
        TripPlanRequest(
            destination="Paris",
            start_date=date(2025, 6, 1),
            end_date=date(2025, 6, 1),
        ),
        _client=mock_client,
    )

    assert isinstance(trip, Trip)
    assert metadata.success is True
    assert any("overlap" in f for f in metadata.validation_failures)


@pytest.mark.anyio
async def test_plan_trip_raises_validation_failed_after_exhausting_repairs():
    """All validation repair attempts fail → ValidationFailedError raised."""
    bad = _overlapping_trip_json()
    mock_client = AsyncMock()
    mock_client.responses.create = AsyncMock(return_value=_text_response(bad))

    with pytest.raises(ValidationFailedError):
        await plan_trip(
            TripPlanRequest(
                destination="Paris",
                start_date=date(2025, 6, 1),
                end_date=date(2025, 6, 1),
            ),
            _client=mock_client,
        )


@pytest.mark.anyio
async def test_validation_failed_error_carries_failures():
    """ValidationFailedError.failures contains the validation error messages."""
    bad = _overlapping_trip_json()
    mock_client = AsyncMock()
    mock_client.responses.create = AsyncMock(return_value=_text_response(bad))

    with pytest.raises(ValidationFailedError) as exc_info:
        await plan_trip(
            TripPlanRequest(
                destination="Paris",
                start_date=date(2025, 6, 1),
                end_date=date(2025, 6, 1),
            ),
            _client=mock_client,
        )

    assert exc_info.value.failures


# ---------------------------------------------------------------------------
# plan_trip — max iterations
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_plan_trip_raises_max_iterations_when_only_tool_calls():
    """Agent loops indefinitely making tool calls → MaxIterationsError."""
    from app.tools.models import GeocodingLocation

    geo_result = GeocodingLocation(
        name="Paris", latitude=48.8566, longitude=2.3522, country="France", admin1=None
    )
    # Always return a tool call, never a final message
    mock_client = AsyncMock()
    mock_client.responses.create = AsyncMock(
        return_value=_tool_call_response("geocode_location", {"query": "Paris"})
    )

    with (
        patch("app.agent.tools.geocode_location", return_value=geo_result),
        pytest.raises(MaxIterationsError),
    ):
        await plan_trip(
            TripPlanRequest(
                destination="Paris",
                start_date=date(2025, 6, 1),
                end_date=date(2025, 6, 1),
            ),
            _client=mock_client,
        )

    # Should have been called MAX_AGENT_ITERATIONS times
    assert mock_client.responses.create.call_count == MAX_AGENT_ITERATIONS


@pytest.mark.anyio
async def test_plan_trip_raises_planning_error_on_empty_output():
    """Agent produces neither tool calls nor message → PlanningError."""
    mock_client = AsyncMock()
    mock_client.responses.create = AsyncMock(return_value=_empty_response())

    with pytest.raises(PlanningError, match="no output"):
        await plan_trip(
            TripPlanRequest(
                destination="Paris",
                start_date=date(2025, 6, 1),
                end_date=date(2025, 6, 1),
            ),
            _client=mock_client,
        )


@pytest.mark.anyio
async def test_plan_trip_raises_planning_error_on_api_failure():
    """OpenAI API raises an exception → PlanningError."""
    mock_client = AsyncMock()
    mock_client.responses.create = AsyncMock(side_effect=RuntimeError("API down"))

    with pytest.raises(PlanningError, match="OpenAI API error"):
        await plan_trip(
            TripPlanRequest(
                destination="Paris",
                start_date=date(2025, 6, 1),
                end_date=date(2025, 6, 1),
            ),
            _client=mock_client,
        )


# ---------------------------------------------------------------------------
# plan_trip — metadata tracking
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_metadata_tracks_multiple_tool_calls():
    from app.tools.models import GeocodingLocation, Place

    geo_result = GeocodingLocation(
        name="Paris", latitude=48.8566, longitude=2.3522, country="France", admin1=None
    )

    tool_resp_1 = _tool_call_response(
        "geocode_location", {"query": "Paris"}, call_id="call_1"
    )
    tool_resp_2 = _tool_call_response(
        "search_places", {"query": "museums in Paris"}, call_id="call_2"
    )
    text_resp = _text_response(VALID_TRIP_JSON)

    mock_client = AsyncMock()
    mock_client.responses.create = AsyncMock(
        side_effect=[tool_resp_1, tool_resp_2, text_resp]
    )

    with (
        patch("app.agent.tools.geocode_location", return_value=geo_result),
        patch("app.agent.tools.search_places", return_value=[]),
    ):
        _, metadata = await plan_trip(
            TripPlanRequest(
                destination="Paris",
                start_date=date(2025, 6, 1),
                end_date=date(2025, 6, 1),
            ),
            _client=mock_client,
        )

    assert metadata.tool_call_count == 2
    assert "geocode_location" in metadata.tools_called
    assert "search_places" in metadata.tools_called
    assert metadata.success is True


# ---------------------------------------------------------------------------
# replan_trip — happy path
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_replan_trip_returns_replan_result():
    original = _make_trip_from_json()

    # Updated JSON: add a new activity on a new second day
    updated_data = json.loads(VALID_TRIP_JSON)
    updated_data["end_date"] = "2025-06-02"
    updated_data["days"].append(
        {
            "date": "2025-06-02",
            "activities": [
                {
                    "name": "Louvre Museum",
                    "location": "Louvre, Paris",
                    "start_time": "10:00:00",
                    "end_time": "13:00:00",
                    "estimated_cost": 17.0,
                    "category": "museum",
                    "locked": False,
                    "notes": None,
                }
            ],
        }
    )
    # Expand original trip date range to match
    original_data = json.loads(VALID_TRIP_JSON)
    original_data["end_date"] = "2025-06-02"
    original_data["days"].append({"date": "2025-06-02", "activities": []})
    original = _make_trip_from_json(json.dumps(original_data))

    updated_json = json.dumps(updated_data)

    mock_client = AsyncMock()
    mock_client.responses.create = AsyncMock(return_value=_text_response(updated_json))

    result = await replan_trip(original, "Add Louvre Museum on day 2", _client=mock_client)

    assert isinstance(result, ReplanResult)
    assert isinstance(result.trip, Trip)
    assert isinstance(result.change_summary, TripChangeSummary)


@pytest.mark.anyio
async def test_replan_trip_preserves_locked_activities():
    """Locked activities must survive replanning unchanged."""
    original_data = json.loads(VALID_TRIP_JSON)
    original_data["days"][0]["activities"][0]["locked"] = True  # Eiffel Tower locked

    original = _make_trip_from_json(json.dumps(original_data))

    # Updated trip keeps the locked activity intact
    updated_data = json.loads(json.dumps(original_data))
    mock_client = AsyncMock()
    mock_client.responses.create = AsyncMock(
        return_value=_text_response(json.dumps(updated_data))
    )

    result = await replan_trip(original, "Remove the lunch", _client=mock_client)
    assert isinstance(result.trip, Trip)


@pytest.mark.anyio
async def test_replan_trip_prompt_includes_locked_names():
    """Verify that locked activity names appear in the replan prompt."""
    original_data = json.loads(VALID_TRIP_JSON)
    original_data["days"][0]["activities"][0]["locked"] = True  # "Eiffel Tower" locked

    original = _make_trip_from_json(json.dumps(original_data))

    mock_client = AsyncMock()
    mock_client.responses.create = AsyncMock(
        return_value=_text_response(json.dumps(original_data))
    )

    await replan_trip(original, "Change something", _client=mock_client)

    # The first call's input should contain the locked name
    first_call_args = mock_client.responses.create.call_args_list[0]
    input_messages = first_call_args.kwargs.get("input", [])
    user_content = input_messages[0]["content"]
    assert "Eiffel Tower" in user_content


# ---------------------------------------------------------------------------
# _compute_change_summary
# ---------------------------------------------------------------------------


def test_compute_change_summary_no_changes():
    trip = _make_trip_from_json()
    summary = _compute_change_summary(trip, trip)
    assert summary.activities_added == 0
    assert summary.activities_removed == 0
    assert summary.activities_changed == 0
    assert summary.summary == "No changes"


def test_compute_change_summary_added_activity():
    original = _make_trip_from_json()

    updated_data = json.loads(VALID_TRIP_JSON)
    updated_data["days"][0]["activities"].append(
        {
            "name": "Dinner",
            "location": "Restaurant, Paris",
            "start_time": "19:00:00",
            "end_time": "21:00:00",
            "estimated_cost": 40.0,
            "category": "food",
            "locked": False,
            "notes": None,
        }
    )
    updated = _make_trip_from_json(json.dumps(updated_data))

    summary = _compute_change_summary(original, updated)
    assert summary.activities_added == 1
    assert summary.activities_removed == 0
    assert "added" in summary.summary


def test_compute_change_summary_removed_activity():
    original_data = json.loads(VALID_TRIP_JSON)
    updated_data = json.loads(VALID_TRIP_JSON)
    updated_data["days"][0]["activities"] = [original_data["days"][0]["activities"][0]]

    original = _make_trip_from_json(json.dumps(original_data))
    updated = _make_trip_from_json(json.dumps(updated_data))

    summary = _compute_change_summary(original, updated)
    assert summary.activities_removed == 1
    assert "removed" in summary.summary


def test_compute_change_summary_changed_activity():
    original = _make_trip_from_json()

    updated_data = json.loads(VALID_TRIP_JSON)
    # Change the start time of the first activity
    updated_data["days"][0]["activities"][0]["start_time"] = "10:00:00"
    updated = _make_trip_from_json(json.dumps(updated_data))

    summary = _compute_change_summary(original, updated)
    assert summary.activities_changed == 1
    assert "modified" in summary.summary


def test_compute_change_summary_budget_difference():
    original = _make_trip_from_json()  # Eiffel Tower 25 + Lunch 20 = 45

    updated_data = json.loads(VALID_TRIP_JSON)
    updated_data["days"][0]["activities"][0]["estimated_cost"] = 50.0  # was 25
    updated = _make_trip_from_json(json.dumps(updated_data))

    summary = _compute_change_summary(original, updated)
    assert abs(summary.budget_difference - 25.0) < 0.01


def test_compute_change_summary_locked_activity_changed():
    original_data = json.loads(VALID_TRIP_JSON)
    original_data["days"][0]["activities"][0]["locked"] = True

    updated_data = json.loads(VALID_TRIP_JSON)
    updated_data["days"][0]["activities"][0]["locked"] = True
    updated_data["days"][0]["activities"][0]["start_time"] = "10:00:00"

    original = _make_trip_from_json(json.dumps(original_data))
    updated = _make_trip_from_json(json.dumps(updated_data))

    summary = _compute_change_summary(original, updated)
    assert summary.locked_activities_changed == 1


def test_compute_change_summary_affected_dates():
    original = _make_trip_from_json()

    updated_data = json.loads(VALID_TRIP_JSON)
    updated_data["days"][0]["activities"].append(
        {
            "name": "Dinner",
            "location": "Restaurant, Paris",
            "start_time": "19:00:00",
            "end_time": "21:00:00",
            "estimated_cost": 40.0,
            "category": "food",
            "locked": False,
            "notes": None,
        }
    )
    updated = _make_trip_from_json(json.dumps(updated_data))

    summary = _compute_change_summary(original, updated)
    assert date(2025, 6, 1) in summary.affected_dates


# ---------------------------------------------------------------------------
# AgentRunMetadata
# ---------------------------------------------------------------------------


def test_agent_run_metadata_defaults():
    m = AgentRunMetadata()
    assert m.tools_called == []
    assert m.tool_call_count == 0
    assert m.validation_attempts == 0
    assert m.validation_failures == []
    assert m.success is False
    assert m.error is None


# ---------------------------------------------------------------------------
# TripPlanRequest
# ---------------------------------------------------------------------------


def test_trip_plan_request_defaults():
    req = TripPlanRequest(
        destination="Tokyo",
        start_date=date(2025, 7, 1),
        end_date=date(2025, 7, 5),
    )
    assert req.interests == []
    assert req.food_preferences == []
    assert req.total_budget is None
    assert req.locked_activities == []


def test_trip_plan_request_with_budget():
    req = TripPlanRequest(
        destination="Tokyo",
        start_date=date(2025, 7, 1),
        end_date=date(2025, 7, 5),
        total_budget=Decimal("1500"),
    )
    assert req.total_budget == Decimal("1500")


# ---------------------------------------------------------------------------
# Tool error handling in execute_tool
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_execute_tool_unknown_name():
    from app.agent.tools import execute_tool

    result = await execute_tool("nonexistent_tool", "{}")
    data = json.loads(result)
    assert "error" in data
    assert "nonexistent_tool" in data["error"]


@pytest.mark.anyio
async def test_execute_tool_bad_json_arguments():
    from app.agent.tools import execute_tool

    result = await execute_tool("geocode_location", "not valid json")
    data = json.loads(result)
    assert "error" in data


@pytest.mark.anyio
async def test_execute_tool_geocode_returns_json():
    from app.agent.tools import execute_tool
    from app.tools.models import GeocodingLocation

    geo = GeocodingLocation(
        name="Paris", latitude=48.8566, longitude=2.3522, country="France", admin1=None
    )
    with patch("app.agent.tools.geocode_location", return_value=geo):
        result = await execute_tool("geocode_location", json.dumps({"query": "Paris"}))

    data = json.loads(result)
    assert data["latitude"] == pytest.approx(48.8566)
    assert data["longitude"] == pytest.approx(2.3522)


@pytest.mark.anyio
async def test_execute_tool_search_places_returns_json():
    from app.agent.tools import execute_tool

    with patch("app.agent.tools.search_places", return_value=[]):
        result = await execute_tool(
            "search_places", json.dumps({"query": "museums in Paris"})
        )

    assert json.loads(result) == []


@pytest.mark.anyio
async def test_execute_tool_handles_tool_error():
    from app.agent.tools import execute_tool
    from app.tools.exceptions import GeocodingError

    with patch(
        "app.agent.tools.geocode_location",
        side_effect=GeocodingError("Not found"),
    ):
        result = await execute_tool("geocode_location", json.dumps({"query": "nowhere"}))

    data = json.loads(result)
    assert "error" in data
    assert "Not found" in data["error"]


@pytest.mark.anyio
async def test_execute_tool_get_route():
    from app.agent.tools import execute_tool
    from app.tools.models import Route, TravelMode

    mock_route = Route(
        origin_lat=48.85, origin_lng=2.35,
        destination_lat=48.86, destination_lng=2.36,
        distance_meters=500, duration_seconds=300, travel_mode=TravelMode.WALK,
    )
    with patch("app.agent.tools.get_route", return_value=mock_route):
        result = await execute_tool(
            "get_route",
            json.dumps(
                {
                    "origin_lat": 48.85,
                    "origin_lng": 2.35,
                    "destination_lat": 48.86,
                    "destination_lng": 2.36,
                }
            ),
        )

    data = json.loads(result)
    assert data["duration_seconds"] == 300
    assert data["distance_meters"] == 500


@pytest.mark.anyio
async def test_execute_tool_get_weather_forecast():
    from app.agent.tools import execute_tool
    from app.tools.models import DailyWeather, WeatherCondition, WeatherForecast

    forecast = WeatherForecast(
        latitude=48.8566,
        longitude=2.3522,
        timezone="Europe/Paris",
        days=[
            DailyWeather(
                date=date(2025, 6, 1),
                condition=WeatherCondition.CLEAR,
                weather_code=0,
                temperature_max=22.0,
                temperature_min=15.0,
                precipitation_mm=0.0,
                precipitation_probability=0,
            )
        ],
    )
    with patch("app.agent.tools.get_weather_forecast", return_value=forecast):
        result = await execute_tool(
            "get_weather_forecast",
            json.dumps(
                {
                    "latitude": 48.8566,
                    "longitude": 2.3522,
                    "start_date": "2025-06-01",
                    "end_date": "2025-06-01",
                }
            ),
        )

    data = json.loads(result)
    assert len(data["days"]) == 1
    assert data["days"][0]["condition"] == "clear"
