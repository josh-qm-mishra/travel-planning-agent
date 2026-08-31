import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..agent.exceptions import PlanningError, ValidationFailedError

logger = logging.getLogger(__name__)

_PLANNING_ERROR_MSG = "Trip planning failed. Please try again."
_REPLAN_ERROR_MSG = "Trip replanning failed. Please try again."
from ..agent.models import TripPlanRequest
from ..agent.planner import plan_trip, replan_trip
from ..db.deps import get_db
from ..db.models import TripRecord
from ..db.repository import TripRepository
from ..models.trip import Trip
from .models import CreateTripResponse, ReplanRequest, ReplanResponse, TripResponse

router = APIRouter(prefix="/trips", tags=["trips"])


def _record_to_trip(record: TripRecord) -> Trip:
    return Trip(**json.loads(record.trip_data))


def _record_to_response(record: TripRecord) -> TripResponse:
    return TripResponse(
        id=record.id,
        trip=_record_to_trip(record),
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@router.post("", response_model=CreateTripResponse, status_code=201)
async def create_trip(
    request: TripPlanRequest,
    db: AsyncSession = Depends(get_db),
) -> CreateTripResponse:
    try:
        trip, metadata = await plan_trip(request)
    except ValidationFailedError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except PlanningError as exc:
        logger.error("plan_trip failed: %s", exc)
        raise HTTPException(status_code=502, detail=_PLANNING_ERROR_MSG)

    record = await TripRepository(db).create(trip)
    return CreateTripResponse(
        id=record.id,
        trip=_record_to_trip(record),
        created_at=record.created_at,
        updated_at=record.updated_at,
        agent_run=metadata,
    )


@router.get("", response_model=list[TripResponse])
async def list_trips(db: AsyncSession = Depends(get_db)) -> list[TripResponse]:
    records = await TripRepository(db).list_all()
    return [_record_to_response(r) for r in records]


@router.get("/{trip_id}", response_model=TripResponse)
async def get_trip(
    trip_id: str,
    db: AsyncSession = Depends(get_db),
) -> TripResponse:
    record = await TripRepository(db).get(trip_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Trip not found")
    return _record_to_response(record)


@router.post("/{trip_id}/replan", response_model=ReplanResponse)
async def replan_trip_endpoint(
    trip_id: str,
    request: ReplanRequest,
    db: AsyncSession = Depends(get_db),
) -> ReplanResponse:
    repo = TripRepository(db)
    record = await repo.get(trip_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Trip not found")

    existing_trip = _record_to_trip(record)
    try:
        result = await replan_trip(existing_trip, request.change_request)
    except ValidationFailedError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except PlanningError as exc:
        logger.error("replan_trip failed for %s: %s", trip_id, exc)
        raise HTTPException(status_code=502, detail=_REPLAN_ERROR_MSG)

    updated = await repo.update(trip_id, result.trip)
    return ReplanResponse(
        id=updated.id,
        trip=_record_to_trip(updated),
        created_at=updated.created_at,
        updated_at=updated.updated_at,
        change_summary=result.change_summary,
    )
