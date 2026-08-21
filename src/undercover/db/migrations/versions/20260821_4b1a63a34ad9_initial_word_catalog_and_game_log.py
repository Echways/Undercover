"""Начальная схема: словарь игры и журнал партий.

Revision ID: 4b1a63a34ad9
Revises:
Create Date: 2026-08-21 01:17:15.528684
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "4b1a63a34ad9"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_categories")),
        sa.UniqueConstraint("slug", name=op.f("uq_categories_slug")),
    )
    op.create_table(
        "words",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("difficulty", sa.SmallInteger(), server_default=sa.text("1"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.CheckConstraint("difficulty BETWEEN 1 AND 3", name=op.f("ck_words_difficulty_range")),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            name=op.f("fk_words_category_id_categories"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_words")),
        sa.UniqueConstraint("category_id", "text", name=op.f("uq_words_category_id_text")),
    )
    op.create_index(
        "ix_words_active_by_category",
        "words",
        ["category_id"],
        unique=False,
        postgresql_where=sa.text("is_active"),
    )
    op.create_table(
        "game_sessions_log",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("host_user_id", sa.BigInteger(), nullable=False),
        sa.Column("players_count", sa.SmallInteger(), nullable=False),
        sa.Column("spies_count", sa.SmallInteger(), nullable=False),
        sa.Column("word_id", sa.Integer(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["word_id"], ["words.id"], name=op.f("fk_game_sessions_log_word_id_words")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_game_sessions_log")),
    )
    op.create_table(
        "spy_hints",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("word_id", sa.Integer(), nullable=False),
        sa.Column("hint_text", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["word_id"], ["words.id"], name=op.f("fk_spy_hints_word_id_words"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_spy_hints")),
        sa.UniqueConstraint("word_id", "hint_text", name=op.f("uq_spy_hints_word_id_hint_text")),
    )


def downgrade() -> None:
    op.drop_table("spy_hints")
    op.drop_table("game_sessions_log")
    op.drop_index(
        "ix_words_active_by_category", table_name="words", postgresql_where=sa.text("is_active")
    )
    op.drop_table("words")
    op.drop_table("categories")
