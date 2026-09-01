import json
import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ..agent.exceptions import PlanningError, ValidationFailedError
from ..agent.models import TripPlanRequest
from ..agent.planner import plan_trip, replan_trip
from ..db.deps import get_db
from ..db.models import TripRecord
from ..db.repository import ConflictError, TripRepository
from ..models.trip import Trip
from .models import CreateTripResponse, ReplanRequest, ReplanResponse, TripResponse

logger = logging.getLogger(__name__)

_PLANNING_ERROR_MSG = "Trip planning failed. Please try again."
_REPLAN_ERROR_MSG = "Trip replanning failed. Please try again."

router = APIRouter(prefix="/trips", tags=["trips"])


def _request_id(request: Request) -> str:
    """Return the X-Request-ID header value if present, else an empty string."""
    return request.headers.get("x-request-id", "")


def _record_to_trip(record: TripRecord) -> Trip:
    return Trip(**json.loads(record.trip_data))


def _record_to_response(record: TripRecord) -> TripResponse:
    return TripResponse(
        id=record.id,
        trip=_record_to_trip(record),
        version=record.version,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@router.post("", response_model=CreateTripResponse, status_code=201)
async def create_trip(
    request_body: TripPlanRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> CreateTripResponse:
    rid = _request_id(request)
    logger.info(
        "trip_planning_started destination=%r days=%d request_id=%s",
        request_body.destination,
        (request_body.end_date - request_body.start_date).days + 1,
        rid,
    )
    t0 = time.monotonic()
    try:
        trip, metadata = await plan_trip(request_body)
    except ValidationFailedError as exc:
        logger.warning(
            "trip_planning_validation_failed destination=%r request_id=%s error=%s",
            request_body.destination,
            rid,
            exc,
        )
        raise HTTPException(status_code=422, detail=str(exc))
    except PlanningError as exc:
        logger.error(
            "trip_planning_failed destination=%r duration_s=%.1f request_id=%s",
            request_body.destination,
            time.monotonic() - t0,
            rid,
        )
        raise HTTPException(status_code=502, detail=_PLANNING_ERROR_MSG)

    elapsed = time.monotonic() - t0
    logger.info(
        "trip_planning_succeeded destination=%r duration_s=%.1f tools=%d "
        "validation_attempts=%d request_id=%s",
        request_body.destination,
        elapsed,
        metadata.tool_call_count,
        metadata.validation_attempts,
        rid,
    )

    record = await TripRepository(db).create(trip)
    return CreateTripResponse(
        id=record.id,
        trip=_record_to_trip(record),
        version=record.version,
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
    request_body: ReplanRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ReplanResponse:
    rid = _request_id(request)
    repo = TripRepository(db)
    record = await repo.get(trip_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Trip not found")

    logger.info(
        "trip_replan_started trip_id=%s expected_version=%s request_id=%s",
        trip_id,
        request_body.expected_version,
        rid,
    )
    t0 = time.monotonic()
    existing_trip = _record_to_trip(record)

    try:
        result = await replan_trip(existing_trip, request_body.change_request)
    except ValidationFailedError as exc:
        logger.warning(
            "trip_replan_validation_failed trip_id=%s request_id=%s error=%s",
            trip_id,
            rid,
            exc,
        )
        raise HTTPException(status_code=422, detail=str(exc))
    except PlanningError as exc:
        logger.error(
            "trip_replan_failed trip_id=%s duration_s=%.1f request_id=%s",
            trip_id,
            time.monotonic() - t0,
            rid,
        )
        raise HTTPException(status_code=502, detail=_REPLAN_ERROR_MSG)

    try:
        updated = await repo.update(trip_id, result.trip, request_body.expected_version)
    except ConflictError as exc:
        logger.warning(
            "trip_replan_conflict trip_id=%s expected_version=%s request_id=%s",
            trip_id,
            request_body.expected_version,
            rid,
        )
        raise HTTPException(
            status_code=409,
            detail="Trip was modified by another request. Refresh and try again.",
        )

    elapsed = time.monotonic() - t0
    logger.info(
        "trip_replan_succeeded trip_id=%s new_version=%d duration_s=%.1f "
        "activities_added=%d activities_removed=%d request_id=%s",
        trip_id,
        updated.version,
        elapsed,
        result.change_summary.activities_added,
        result.change_summary.activities_removed,
        rid,
    )

    return ReplanResponse(
        id=updated.id,
        trip=_record_to_trip(updated),
        version=updated.version,
        created_at=updated.created_at,
        updated_at=updated.updated_at,
        change_summary=result.change_summary,
    )
