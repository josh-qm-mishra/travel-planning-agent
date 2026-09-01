from datetime import date
from pydantic import BaseModel, Field, field_validator, model_validator

from ..models.trip import Activity, Money, Pace, Trip, TripConstraints, WalkingTolerance

_MAX_TAG_COUNT = 20
_MAX_TAG_LENGTH = 60
_MAX_DESTINATION_LENGTH = 200
_MAX_TRIP_DAYS = 30


class TripPlanRequest(BaseModel):
    """Input model for requesting a new trip itinerary."""

    destination: str = Field(..., min_length=1, max_length=_MAX_DESTINATION_LENGTH)
    start_date: date
    end_date: date
    total_budget: Money | None = Field(default=None, le=1_000_000)
    interests: list[str] = Field(default_factory=list, max_length=_MAX_TAG_COUNT)
    food_preferences: list[str] = Field(default_factory=list, max_length=_MAX_TAG_COUNT)
    pace: Pace = Pace.MODERATE
    morning_preference: bool = True
    walking_tolerance: WalkingTolerance = WalkingTolerance.MODERATE
    constraints: TripConstraints = Field(default_factory=TripConstraints)
    locked_activities: list[Activity] = Field(default_factory=list)

    @field_validator("interests", "food_preferences", mode="after")
    @classmethod
    def _tags_not_too_long(cls, tags: list[str]) -> list[str]:
        for tag in tags:
            if len(tag) > _MAX_TAG_LENGTH:
                raise ValueError(
                    f"Each tag must be at most {_MAX_TAG_LENGTH} characters; "
                    f"got {len(tag)!r}"
                )
        return tags

    @model_validator(mode="after")
    def _dates_valid(self) -> "TripPlanRequest":
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        delta = (self.end_date - self.start_date).days
        if delta >= _MAX_TRIP_DAYS:
            raise ValueError(
                f"Trip duration must be less than {_MAX_TRIP_DAYS} days; "
                f"requested {delta + 1} days"
            )
        return self


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
