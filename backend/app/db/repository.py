import uuid
from datetime import datetime, timezone

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.trip import Trip
from .models import TripRecord


class TripRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, trip: Trip) -> TripRecord:
        record = TripRecord(
            id=str(uuid.uuid4()),
            destination=trip.destination,
            start_date=trip.start_date,
            end_date=trip.end_date,
            trip_data=trip.model_dump_json(),
        )
        self._session.add(record)
        await self._session.commit()
        await self._session.refresh(record)
        return record

    async def get(self, trip_id: str) -> TripRecord | None:
        result = await self._session.execute(
            select(TripRecord).where(TripRecord.id == trip_id)
        )
        return result.scalar_one_or_none()

    async def update(self, trip_id: str, trip: Trip) -> TripRecord:
        record = await self.get(trip_id)
        if record is None:
            raise ValueError(f"Trip {trip_id!r} not found")
        record.trip_data = trip.model_dump_json()
        record.destination = trip.destination
        record.start_date = trip.start_date
        record.end_date = trip.end_date
        record.updated_at = datetime.now(timezone.utc)
        await self._session.commit()
        await self._session.refresh(record)
        return record

    async def list_all(self) -> list[TripRecord]:
        result = await self._session.execute(
            select(TripRecord).order_by(desc(TripRecord.created_at))
        )
        return list(result.scalars().all())
