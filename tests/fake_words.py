from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

WORD = "пицца"
HINTS = ("её режут на куски", "её заказывают домой")


@dataclass(frozen=True, slots=True)
class FakeHint:
    hint_text: str


@dataclass(frozen=True, slots=True)
class FakeWord:
    id: int
    text: str
    hints: tuple[FakeHint, ...]


@dataclass(frozen=True, slots=True)
class FakeCategory:
    id: int
    title: str


@dataclass(slots=True)
class FakeWords:
    word: FakeWord | None
    categories: tuple[FakeCategory, ...] = ()
    empty_categories: frozenset[int] = frozenset()
    asked_categories: list[int | None] = field(default_factory=list)
    opened: int = 0
    closed: int = 0

    async def get_random_active_word(self, category_id: int | None = None) -> FakeWord | None:
        self.asked_categories.append(category_id)
        if category_id in self.empty_categories:
            return None
        return self.word

    async def list_playable_categories(self) -> Sequence[FakeCategory]:
        return self.categories

    @asynccontextmanager
    async def open(self) -> AsyncIterator["FakeWords"]:
        self.opened += 1
        try:
            yield self
        finally:
            self.closed += 1


def pizza() -> FakeWord:
    return FakeWord(id=42, text=WORD, hints=tuple(FakeHint(hint) for hint in HINTS))


def catalog(*titles: str) -> tuple[FakeCategory, ...]:
    return tuple(
        FakeCategory(id=number, title=title) for number, title in enumerate(titles, start=1)
    )
