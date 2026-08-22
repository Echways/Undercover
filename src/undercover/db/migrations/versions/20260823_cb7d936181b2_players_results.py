"""Результаты игроков в партии

Revision ID: cb7d936181b2
Revises: 824c4caabd78
Create Date: 2026-08-23 00:05:59.231812
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "cb7d936181b2"
down_revision: str | Sequence[str] | None = "824c4caabd78"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "game_player_results",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("game_id", sa.BigInteger(), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("is_spy", sa.Boolean(), nullable=False),
        sa.Column("is_winner", sa.Boolean(), nullable=False),
        sa.Column("out_order", sa.SmallInteger(), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("out_order > 0", name=op.f("ck_game_player_results_out_order_positive")),
        sa.ForeignKeyConstraint(
            ["game_id"],
            ["game_sessions_log.id"],
            name=op.f("fk_game_player_results_game_id_game_sessions_log"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_game_player_results")),
        sa.UniqueConstraint(
            "game_id", "user_id", name=op.f("uq_game_player_results_game_id_user_id")
        ),
    )
    op.create_index(
        "ix_game_player_results_chat_id_finished_at",
        "game_player_results",
        ["chat_id", "finished_at"],
        unique=False,
    )
    op.create_index(
        "ix_game_player_results_chat_id_user_id",
        "game_player_results",
        ["chat_id", "user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_game_player_results_chat_id_user_id", table_name="game_player_results")
    op.drop_index("ix_game_player_results_chat_id_finished_at", table_name="game_player_results")
    op.drop_table("game_player_results")
