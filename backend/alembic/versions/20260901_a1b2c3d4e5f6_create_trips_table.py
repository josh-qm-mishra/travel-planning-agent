"""create trips table

Revision ID: a1b2c3d4e5f6
Revises:
Create Date: 2026-09-01

This is the initial migration. It represents the schema that was previously
created by SQLAlchemy create_all().

For a FRESH database run:
    alembic upgrade head

For an EXISTING database that already has the trips table (pre-Alembic):
    alembic stamp a1b2c3d4e5f6   # mark this revision as already applied
    alembic upgrade head          # apply migration 002 (version column)
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "trips",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("destination", sa.String(255), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("trip_data", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_trips_destination", "trips", ["destination"])
    op.create_index("ix_trips_start_date", "trips", ["start_date"])


def downgrade() -> None:
    op.drop_index("ix_trips_start_date", table_name="trips")
    op.drop_index("ix_trips_destination", table_name="trips")
    op.drop_table("trips")
