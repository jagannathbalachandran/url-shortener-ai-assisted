"""create clicks table

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-30

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

MAX_REFERRER_HOST_LENGTH = 253


def upgrade() -> None:
    """Create the clicks table.

    Only creates a new table/index -- the existing `links` table is never
    altered, so existing link data is untouched by this migration.
    """
    op.create_table(
        "clicks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "link_id",
            sa.Integer(),
            sa.ForeignKey("links.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("clicked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "referrer_host",
            sa.String(length=MAX_REFERRER_HOST_LENGTH),
            nullable=False,
        ),
    )
    op.create_index("ix_clicks_link_id_clicked_at", "clicks", ["link_id", "clicked_at"])


def downgrade() -> None:
    """Drop the clicks table; `links` and its data are left untouched."""
    op.drop_index("ix_clicks_link_id_clicked_at", table_name="clicks")
    op.drop_table("clicks")
