import hashlib
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
from ..rate_limit import SlidingWindowLimiter, get_limiter
from .models import CreateTripResponse, ReplanRequest, ReplanResponse, TripResponse

logger = logging.getLogger(__name__)

_PLANNING_ERROR_MSG = "Trip planning failed. Please try again."
_REPLAN_ERROR_MSG = "Trip replanning failed. Please try again."

router = APIRouter(prefix="/trips", tags=["trips"])


def _request_id(request: Request) -> str:
    """Return the X-Request-ID header value if present, else an empty string."""
    return request.headers.get("x-request-id", "")


def _extract_owner_hash(request: Request) -> str:
    """Hash the X-Client-ID header; raise 401 if missing."""
    client_id = request.headers.get("x-client-id", "").strip()
    if not client_id:
        raise HTTPException(status_code=401, detail="X-Client-ID header is required.")
    return hashlib.sha256(client_id.encode()).hexdigest()


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


async def _check_rate_limit(owner_hash: str, limiter: SlidingWindowLimiter) -> None:
    allowed, retry_after = await limiter.check_and_record(owner_hash)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Too many planning requests. Please wait and try again.",
            headers={"Retry-After": str(retry_after)},
        )


@router.post("", response_model=CreateTripResponse, status_code=201)
async def create_trip(
    request_body: TripPlanRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    limiter: SlidingWindowLimiter = Depends(get_limiter),
) -> CreateTripResponse:
    owner_hash = _extract_owner_hash(request)
    await _check_rate_limit(owner_hash, limiter)

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

    record = await TripRepository(db).create(trip, owner_hash)
    return CreateTripResponse(
        id=record.id,
        trip=_record_to_trip(record),
        version=record.version,
        created_at=record.created_at,
        updated_at=record.updated_at,
        agent_run=metadata,
    )


@router.get("", response_model=list[TripResponse])
async def list_trips(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> list[TripResponse]:
    owner_hash = _extract_owner_hash(request)
    records = await TripRepository(db).list_all(owner_hash)
    return [_record_to_response(r) for r in records]


@router.get("/{trip_id}", response_model=TripResponse)
async def get_trip(
    trip_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> TripResponse:
    owner_hash = _extract_owner_hash(request)
    record = await TripRepository(db).get(trip_id, owner_hash)
    if record is None:
        raise HTTPException(status_code=404, detail="Trip not found")
    return _record_to_response(record)


@router.post("/{trip_id}/replan", response_model=ReplanResponse)
async def replan_trip_endpoint(
    trip_id: str,
    request_body: ReplanRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    limiter: SlidingWindowLimiter = Depends(get_limiter),
) -> ReplanResponse:
    owner_hash = _extract_owner_hash(request)
    await _check_rate_limit(owner_hash, limiter)

    rid = _request_id(request)
    repo = TripRepository(db)
    record = await repo.get(trip_id, owner_hash)
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
        updated = await repo.update(trip_id, result.trip, owner_hash, request_body.expected_version)
    except ConflictError:
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
