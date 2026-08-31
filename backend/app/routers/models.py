from datetime import datetime

from pydantic import BaseModel

from ..agent.models import AgentRunMetadata, TripChangeSummary
from ..models.trip import Trip


class TripResponse(BaseModel):
    """API response envelope for a persisted trip."""

    id: str
    trip: Trip
    created_at: datetime
    updated_at: datetime


class CreateTripResponse(TripResponse):
    """Response for POST /trips — includes agent observability metadata."""

    agent_run: AgentRunMetadata


class ReplanRequest(BaseModel):
    """Request body for POST /trips/{id}/replan."""

    change_request: str


class ReplanResponse(TripResponse):
    """Response for POST /trips/{id}/replan — includes change summary."""

    change_summary: TripChangeSummary
