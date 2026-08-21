from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    MetaData,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
    text as sql_text,
    true,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(Text, unique=True)
    title: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())

    words: Mapped[list["Word"]] = relationship(
        back_populates="category",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Word(Base):
    __tablename__ = "words"
    __table_args__ = (
        UniqueConstraint("category_id", "text"),
        CheckConstraint("difficulty BETWEEN 1 AND 3", name="difficulty_range"),
        Index(
            "ix_words_active_by_category",
            "category_id",
            postgresql_where=sql_text("is_active"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"))
    text: Mapped[str] = mapped_column(Text)
    difficulty: Mapped[int] = mapped_column(
        SmallInteger, default=1, server_default=sql_text("1")
    )
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())

    category: Mapped[Category] = relationship(back_populates="words")
    hints: Mapped[list["SpyHint"]] = relationship(
        back_populates="word",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="SpyHint.id",
    )


class SpyHint(Base):
    __tablename__ = "spy_hints"
    __table_args__ = (UniqueConstraint("word_id", "hint_text"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    word_id: Mapped[int] = mapped_column(ForeignKey("words.id", ondelete="CASCADE"))
    hint_text: Mapped[str] = mapped_column(Text)

    word: Mapped[Word] = relationship(back_populates="hints")


class GameSessionLog(Base):
    __tablename__ = "game_sessions_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger)
    host_user_id: Mapped[int] = mapped_column(BigInteger)
    players_count: Mapped[int] = mapped_column(SmallInteger)
    spies_count: Mapped[int] = mapped_column(SmallInteger)
    word_id: Mapped[int | None] = mapped_column(ForeignKey("words.id"))
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
