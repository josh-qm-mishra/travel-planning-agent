import uuid
from datetime import datetime, timezone

from sqlalchemy import desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.trip import Trip
from .models import TripRecord


class ConflictError(Exception):
    """Raised when an optimistic-concurrency update is rejected.

    The trip was modified by another request between the time it was read and
    the time the update was attempted.  The caller should return HTTP 409.
    """


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
            version=1,
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

    async def update(
        self,
        trip_id: str,
        trip: Trip,
        expected_version: int | None = None,
    ) -> TripRecord:
        """Update a trip record.

        If *expected_version* is provided the update is executed as a
        conditional write:

            UPDATE trips SET ... WHERE id = ? AND version = expected_version

        If the row was already modified by another request the statement
        matches zero rows and ConflictError is raised.  The version counter is
        incremented on every successful update.

        If *expected_version* is None the update is unconditional (no conflict
        detection); this is retained for backward compatibility and test use.
        """
        now = datetime.now(timezone.utc)
        new_values = {
            "trip_data": trip.model_dump_json(),
            "destination": trip.destination,
            "start_date": trip.start_date,
            "end_date": trip.end_date,
            "updated_at": now,
        }

        if expected_version is not None:
            # Conditional write: only update if version matches.
            stmt = (
                update(TripRecord)
                .where(TripRecord.id == trip_id)
                .where(TripRecord.version == expected_version)
                .values(**new_values, version=expected_version + 1)
                .returning(TripRecord)
            )
            result = await self._session.execute(stmt)
            await self._session.commit()
            updated = result.scalar_one_or_none()
            if updated is None:
                # Either the trip doesn't exist or a concurrent update changed
                # the version before we could write.
                existing = await self.get(trip_id)
                if existing is None:
                    raise ValueError(f"Trip {trip_id!r} not found")
                raise ConflictError(
                    f"Trip {trip_id!r} was modified concurrently "
                    f"(expected version {expected_version}, "
                    f"current version {existing.version})"
                )
            return updated
        else:
            # Unconditional update — no optimistic lock.
            record = await self.get(trip_id)
            if record is None:
                raise ValueError(f"Trip {trip_id!r} not found")
            record.trip_data = trip.model_dump_json()
            record.destination = trip.destination
            record.start_date = trip.start_date
            record.end_date = trip.end_date
            record.updated_at = now
            record.version += 1
            await self._session.commit()
            await self._session.refresh(record)
            return record

    async def list_all(self) -> list[TripRecord]:
        result = await self._session.execute(
            select(TripRecord).order_by(desc(TripRecord.created_at))
        )
        return list(result.scalars().all())
