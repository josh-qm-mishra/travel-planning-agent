from .models import TripPlanRequest

# ---------------------------------------------------------------------------
# System prompt — sent as `instructions` on every Responses API call so the
# model always has its role and the expected output schema in context.
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are an expert travel planning assistant. Your job is to create detailed,
realistic, day-by-day travel itineraries using real data from the tools you
have access to.

Available tools:
- geocode_location  : Convert a place name to latitude/longitude
- get_weather_forecast : Daily weather for a date range (needs coordinates)
- search_places     : Find restaurants, museums, attractions near coordinates
- get_route         : Walking/driving travel time between two coordinates

Recommended workflow
1. Geocode the destination to get coordinates.
2. Fetch the weather for the trip dates.
3. Search for places matching the traveler's interests.
4. Build a realistic schedule, checking travel times between venues.

Output format
When you have finished researching, output your answer as a SINGLE JSON object
that matches the Trip schema below — no markdown fences, no explanation.

Trip schema:
{
  "destination": "string",
  "start_date": "YYYY-MM-DD",
  "end_date": "YYYY-MM-DD",
  "total_budget": <number or null>,
  "preferences": {
    "interests": ["string"],
    "food_preferences": ["string"],
    "pace": "relaxed"|"moderate"|"busy",
    "morning_preference": true|false,
    "walking_tolerance": "low"|"moderate"|"high"
  },
  "constraints": {
    "earliest_start_time": "HH:MM:SS"|null,
    "latest_end_time": "HH:MM:SS"|null,
    "maximum_budget": <number or null>
  },
  "days": [
    {
      "date": "YYYY-MM-DD",
      "activities": [
        {
          "name": "string",
          "location": "string (place name or address)",
          "start_time": "HH:MM:SS",
          "end_time": "HH:MM:SS",
          "estimated_cost": <number >= 0>,
          "category": "string",
          "locked": false,
          "notes": "string or null"
        }
      ]
    }
  ]
}

Rules:
- Include every calendar day from start_date to end_date.
- Activities on the same day must not overlap (end_time <= next start_time).
- estimated_cost must be >= 0.
- Set locked=true only for activities explicitly marked as locked in the request.
- Output ONLY the JSON object — no surrounding text.
"""

# ---------------------------------------------------------------------------
# User-facing prompt builders
# ---------------------------------------------------------------------------


def build_planning_prompt(request: TripPlanRequest) -> str:
    lines = [f"Plan a trip to {request.destination}."]
    lines.append(f"Travel dates: {request.start_date} to {request.end_date}.")
    if request.total_budget is not None:
        lines.append(f"Total budget: ${float(request.total_budget):.2f}.")
    if request.interests:
        lines.append(f"Interests: {', '.join(request.interests)}.")
    if request.food_preferences:
        lines.append(f"Food preferences: {', '.join(request.food_preferences)}.")
    lines.append(f"Pace: {request.pace}.")
    lines.append(f"Morning person: {'yes' if request.morning_preference else 'no'}.")
    lines.append(f"Walking tolerance: {request.walking_tolerance}.")
    if request.constraints.earliest_start_time:
        lines.append(f"Do not schedule anything before {request.constraints.earliest_start_time}.")
    if request.constraints.latest_end_time:
        lines.append(f"Do not schedule anything after {request.constraints.latest_end_time}.")
    if request.locked_activities:
        lines.append(
            "\nThe following activities are locked and must appear exactly as given "
            "(same times, set locked=true):"
        )
        for act in request.locked_activities:
            lines.append(
                f"  - {act.name} | {act.start_time}–{act.end_time} "
                f"| {act.location} | locked=true"
            )
    lines.append(
        "\nUse the available tools to research this destination, then output "
        "the complete trip as a single JSON object."
    )
    return "\n".join(lines)


def build_parse_repair_prompt(bad_json: str, error: str) -> str:
    return (
        f"The JSON you produced could not be parsed into a valid Trip:\n\n"
        f"Error: {error}\n\n"
        f"Your output:\n{bad_json}\n\n"
        "Fix the errors and output the corrected Trip JSON — nothing else."
    )


def build_validation_repair_prompt(trip_json: str, failures: list[str]) -> str:
    bullet_list = "\n".join(f"  - {f}" for f in failures)
    return (
        f"The itinerary has validation errors that must be fixed:\n\n"
        f"{bullet_list}\n\n"
        f"Current itinerary:\n{trip_json}\n\n"
        "Fix every error and output the corrected Trip JSON — nothing else."
    )


def build_replan_prompt(
    trip_json: str,
    change_request: str,
    locked_activity_names: list[str],
) -> str:
    locked_section = ""
    if locked_activity_names:
        names = "\n".join(f"  - {n}" for n in locked_activity_names)
        locked_section = (
            f"\nCRITICAL — the following activities are LOCKED. "
            f"You must not move, change, or remove them:\n{names}\n"
        )
    return (
        f"Here is the existing trip:\n{trip_json}\n\n"
        f"The traveller requests this change:\n{change_request}\n"
        f"{locked_section}\n"
        "Make the minimal changes needed to fulfil the request. "
        "Locked activities must keep their exact date, start_time, end_time, and locked=true. "
        "Output the complete updated Trip JSON — nothing else."
    )
