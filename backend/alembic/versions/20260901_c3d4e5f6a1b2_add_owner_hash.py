"""add owner_hash column for anonymous trip ownership

Revision ID: c3d4e5f6a1b2
Revises: b2c3d4e5f6a1
Create Date: 2026-09-01

Adds owner_hash (SHA-256 of the browser's X-Client-ID) so each trip is
associated with a specific anonymous browser session.

Existing rows get owner_hash='' (empty string) — they are effectively
orphaned: no valid browser request can claim them since hashing any
non-empty string produces a different digest.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c3d4e5f6a1b2"
down_revision: Union[str, None] = "b2c3d4e5f6a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "trips",
        sa.Column("owner_hash", sa.String(64), nullable=False, server_default=""),
    )
    op.create_index("ix_trips_owner_hash", "trips", ["owner_hash"])


def downgrade() -> None:
    op.drop_index("ix_trips_owner_hash", table_name="trips")
    op.drop_column("trips", "owner_hash")
