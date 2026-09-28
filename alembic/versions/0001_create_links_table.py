"""create links table

Revision ID: 0001
Revises:
Create Date: 2026-09-28

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

CODE_LENGTH = 7
MAX_ORIGINAL_URL_LENGTH = 2048


def upgrade() -> None:
    """Create the links table."""
    op.create_table(
        "links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=CODE_LENGTH), nullable=False),
        sa.Column(
            "original_url", sa.String(length=MAX_ORIGINAL_URL_LENGTH), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_links_code", "links", ["code"], unique=True)


def downgrade() -> None:
    """Drop the links table."""
    op.drop_index("ix_links_code", table_name="links")
    op.drop_table("links")
