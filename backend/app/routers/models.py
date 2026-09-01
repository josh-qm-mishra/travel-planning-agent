from datetime import datetime

from pydantic import BaseModel, Field

from ..agent.models import AgentRunMetadata, TripChangeSummary
from ..models.trip import Trip


class TripResponse(BaseModel):
    """API response envelope for a persisted trip."""

    id: str
    trip: Trip
    version: int
    created_at: datetime
    updated_at: datetime


class CreateTripResponse(TripResponse):
    """Response for POST /trips — includes agent observability metadata."""

    agent_run: AgentRunMetadata


class ReplanRequest(BaseModel):
    """Request body for POST /trips/{id}/replan."""

    change_request: str = Field(..., min_length=1, max_length=2000)
    # When provided, the update is rejected with 409 if the trip has been
    # modified since the client last read it (optimistic concurrency control).
    expected_version: int | None = Field(default=None, ge=1)


class ReplanResponse(TripResponse):
    """Response for POST /trips/{id}/replan — includes change summary."""

    change_summary: TripChangeSummary
