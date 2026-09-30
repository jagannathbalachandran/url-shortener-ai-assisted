"""add expires_at to links

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-30

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Add a nullable expires_at column to links.

    Batch mode (explicit, independent of env.py's render_as_batch) so this
    is correct on SQLite (which can't ALTER TABLE ADD COLUMN in place for
    every case) and a plain ALTER TABLE on Postgres. Existing rows get NULL,
    so they keep never expiring (T-07 / ADR-002 D2).
    """
    with op.batch_alter_table("links") as batch_op:
        batch_op.add_column(
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    """Drop expires_at; existing link rows and their other columns are untouched."""
    with op.batch_alter_table("links") as batch_op:
        batch_op.drop_column("expires_at")
