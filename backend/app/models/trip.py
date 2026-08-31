from datetime import date, time
from decimal import Decimal
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field, PlainSerializer, model_validator


# ---------------------------------------------------------------------------
# Money type
#   Stored as Decimal (exact arithmetic), serialized as float in JSON so the
#   API and agent always receive a JSON number rather than a quoted string.
# ---------------------------------------------------------------------------

Money = Annotated[
    Decimal,
    Field(ge=0),
    PlainSerializer(lambda x: float(x), return_type=float, when_used="json"),
]


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class Pace(StrEnum):
    RELAXED = "relaxed"
    MODERATE = "moderate"
    BUSY = "busy"


class WalkingTolerance(StrEnum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"


# ---------------------------------------------------------------------------
# Preference / constraint models
# ---------------------------------------------------------------------------


class TripPreferences(BaseModel):
    interests: list[str] = Field(default_factory=list)
    food_preferences: list[str] = Field(default_factory=list)
    pace: Pace = Pace.MODERATE
    morning_preference: bool = True
    walking_tolerance: WalkingTolerance = WalkingTolerance.MODERATE


class TripConstraints(BaseModel):
    earliest_start_time: time | None = None
    latest_end_time: time | None = None
    maximum_budget: Money | None = None


# ---------------------------------------------------------------------------
# Activity
# ---------------------------------------------------------------------------


class Activity(BaseModel):
    name: str
    location: str
    start_time: time
    end_time: time
    estimated_cost: Money = Decimal("0")
    category: str
    locked: bool = False
    notes: str | None = None

    @model_validator(mode="after")
    def _end_after_start(self) -> "Activity":
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


# ---------------------------------------------------------------------------
# TripDay
# ---------------------------------------------------------------------------


class TripDay(BaseModel):
    date: date
    activities: list[Activity] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Trip
# ---------------------------------------------------------------------------


class Trip(BaseModel):
    destination: str
    start_date: date
    end_date: date
    total_budget: Money | None = None
    preferences: TripPreferences = Field(default_factory=TripPreferences)
    constraints: TripConstraints = Field(default_factory=TripConstraints)
    days: list[TripDay] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_trip(self) -> "Trip":
        if self.end_date < self.start_date:
            raise ValueError("end_date cannot be before start_date")

        seen: set[date] = set()
        for day in self.days:
            if not (self.start_date <= day.date <= self.end_date):
                raise ValueError(
                    f"TripDay date {day.date} is outside the trip range "
                    f"[{self.start_date}, {self.end_date}]"
                )
            if day.date in seen:
                raise ValueError(f"Duplicate TripDay date: {day.date}")
            seen.add(day.date)

        return self
