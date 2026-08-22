"""Победитель партии в журнале.

Revision ID: 824c4caabd78
Revises: 4b1a63a34ad9
Create Date: 2026-08-22 23:16:20.797373
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "824c4caabd78"
down_revision: str | Sequence[str] | None = "4b1a63a34ad9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("game_sessions_log", sa.Column("winner", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("game_sessions_log", "winner")
