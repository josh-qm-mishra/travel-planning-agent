"""OpenAI tool definitions and dispatcher for the planning agent.

TOOL_DEFINITIONS is the list passed to the Responses API ``tools`` parameter.
execute_tool() dispatches a tool call by name, runs the real travel-tool
function, and returns the result as a JSON string.
"""
import json
from datetime import date

from ..tools import geocode_location, get_route, get_weather_forecast, search_places
from ..tools.exceptions import ToolError
from ..tools.models import TravelMode

# ---------------------------------------------------------------------------
# Tool schemas (OpenAI function-tool format)
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS: list[dict] = [
    {
        "type": "function",
        "name": "geocode_location",
        "description": (
            "Convert a place name or address into geographic coordinates "
            "(latitude and longitude)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Location name, e.g. 'Paris, France'",
                }
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        "strict": False,
    },
    {
        "type": "function",
        "name": "get_weather_forecast",
        "description": "Fetch daily weather forecast for a coordinate pair and date range.",
        "parameters": {
            "type": "object",
            "properties": {
                "latitude": {"type": "number"},
                "longitude": {"type": "number"},
                "start_date": {
                    "type": "string",
                    "description": "ISO date YYYY-MM-DD",
                },
                "end_date": {
                    "type": "string",
                    "description": "ISO date YYYY-MM-DD",
                },
            },
            "required": ["latitude", "longitude", "start_date", "end_date"],
            "additionalProperties": False,
        },
        "strict": False,
    },
    {
        "type": "function",
        "name": "search_places",
        "description": (
            "Search for places of interest (museums, restaurants, attractions) "
            "optionally near a geographic location."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "latitude": {
                    "type": "number",
                    "description": "Optional bias centre latitude",
                },
                "longitude": {
                    "type": "number",
                    "description": "Optional bias centre longitude",
                },
                "max_results": {"type": "integer", "default": 10},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        "strict": False,
    },
    {
        "type": "function",
        "name": "get_route",
        "description": "Calculate travel time and distance between two coordinates.",
        "parameters": {
            "type": "object",
            "properties": {
                "origin_lat": {"type": "number"},
                "origin_lng": {"type": "number"},
                "destination_lat": {"type": "number"},
                "destination_lng": {"type": "number"},
                "travel_mode": {
                    "type": "string",
                    "enum": ["drive", "walk", "bicycle", "transit"],
                    "default": "walk",
                },
            },
            "required": [
                "origin_lat",
                "origin_lng",
                "destination_lat",
                "destination_lng",
            ],
            "additionalProperties": False,
        },
        "strict": False,
    },
]

# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


async def execute_tool(name: str, arguments_json: str) -> str:
    """Execute a named tool with JSON-encoded arguments.

    Always returns a JSON string — on error it returns ``{"error": "..."}``.
    This ensures the model always receives structured feedback even when a tool
    call fails, which is safer than raising an exception mid-loop.
    """
    try:
        args = json.loads(arguments_json)
    except json.JSONDecodeError as exc:
        return json.dumps({"error": f"Could not parse tool arguments: {exc}"})

    try:
        if name == "geocode_location":
            result = await geocode_location(args["query"])
            return result.model_dump_json()

        if name == "get_weather_forecast":
            result = await get_weather_forecast(
                latitude=args["latitude"],
                longitude=args["longitude"],
                start_date=date.fromisoformat(args["start_date"]),
                end_date=date.fromisoformat(args["end_date"]),
            )
            return result.model_dump_json()

        if name == "search_places":
            results = await search_places(
                query=args["query"],
                latitude=args.get("latitude"),
                longitude=args.get("longitude"),
                max_results=args.get("max_results", 10),
            )
            return json.dumps([p.model_dump(mode="json") for p in results])

        if name == "get_route":
            result = await get_route(
                origin_lat=args["origin_lat"],
                origin_lng=args["origin_lng"],
                destination_lat=args["destination_lat"],
                destination_lng=args["destination_lng"],
                travel_mode=TravelMode(args.get("travel_mode", "walk")),
            )
            return result.model_dump_json()

        return json.dumps({"error": f"Unknown tool: {name}"})

    except ToolError as exc:
        return json.dumps({"error": str(exc)})
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": f"Tool execution failed: {exc}"})
