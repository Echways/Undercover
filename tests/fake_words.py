from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

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


@dataclass(slots=True)
class FakeWords:
    word: FakeWord | None
    opened: int = 0
    closed: int = 0

    async def get_random_active_word(self, category_id: int | None = None) -> FakeWord | None:
        return self.word

    @asynccontextmanager
    async def open(self) -> AsyncIterator["FakeWords"]:
        self.opened += 1
        try:
            yield self
        finally:
            self.closed += 1


def pizza() -> FakeWord:
    return FakeWord(id=42, text=WORD, hints=tuple(FakeHint(hint) for hint in HINTS))
