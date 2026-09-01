"""add version column for optimistic concurrency

Revision ID: b2c3d4e5f6a1
Revises: a1b2c3d4e5f6
Create Date: 2026-09-01

Adds an integer version counter to the trips table.
The version is incremented on every successful replan, and the replan
endpoint uses an optimistic concurrency check (WHERE version = expected)
to return HTTP 409 if the trip was concurrently modified.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f6a1"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # All existing rows get version=1; new rows also start at 1.
    op.add_column(
        "trips",
        sa.Column(
            "version",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
    )


def downgrade() -> None:
    op.drop_column("trips", "version")
