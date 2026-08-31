from datetime import date
from pydantic import BaseModel, Field

from ..models.trip import Activity, Money, Pace, Trip, TripConstraints, WalkingTolerance


class TripPlanRequest(BaseModel):
    """Input model for requesting a new trip itinerary."""

    destination: str
    start_date: date
    end_date: date
    total_budget: Money | None = None
    interests: list[str] = Field(default_factory=list)
    food_preferences: list[str] = Field(default_factory=list)
    pace: Pace = Pace.MODERATE
    morning_preference: bool = True
    walking_tolerance: WalkingTolerance = WalkingTolerance.MODERATE
    constraints: TripConstraints = Field(default_factory=TripConstraints)
    # Activities that must appear in the generated trip exactly as specified.
    locked_activities: list[Activity] = Field(default_factory=list)


class TripChangeSummary(BaseModel):
    """Structured summary of what changed between an original and a replanned trip."""

    activities_added: int = 0
    activities_removed: int = 0
    activities_changed: int = 0
    affected_dates: list[date] = Field(default_factory=list)
    # Positive means the updated trip costs more; negative means less.
    budget_difference: float | None = None
    # Should always be 0 for a valid replan — exposed so callers can assert it.
    locked_activities_changed: int = 0
    summary: str = ""


class ReplanResult(BaseModel):
    """Output of a replanning operation."""

    trip: Trip
    change_summary: TripChangeSummary


class AgentRunMetadata(BaseModel):
    """Lightweight observability record for one planning / replanning run."""

    tools_called: list[str] = Field(default_factory=list)
    tool_call_count: int = 0
    validation_attempts: int = 0
    validation_failures: list[str] = Field(default_factory=list)
    success: bool = False
    error: str | None = None
