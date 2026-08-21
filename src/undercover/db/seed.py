import asyncio
import logging
from dataclasses import dataclass

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from undercover.config import ConfigurationError, load_settings
from undercover.db.models import Category, SpyHint, Word
from undercover.db.session import create_engine, create_sessionmaker
from undercover.log import DEFAULT_LEVEL, configure_logging

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class WordSeed:
    text: str
    difficulty: int
    hints: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CategorySeed:
    slug: str
    title: str
    words: tuple[WordSeed, ...]


@dataclass(frozen=True, slots=True)
class SeedReport:
    categories: int
    words: int
    hints: int


CATALOG: tuple[CategorySeed, ...] = (
    CategorySeed(
        slug="cities",
        title="Города",
        words=(
            WordSeed(
                "Париж",
                1,
                ("туда едут за романтикой", "многие узнают его по одному силуэту"),
            ),
            WordSeed(
                "Токио",
                2,
                ("там очень много людей на небольшой площади", "техника там появляется раньше"),
            ),
            WordSeed(
                "Венеция",
                2,
                ("там передвигаются не так, как везде", "туда лучше ехать не в жару"),
            ),
            WordSeed(
                "Нью-Йорк",
                1,
                ("там задирают голову, чтобы увидеть верх", "оттуда половина знакомых фильмов"),
            ),
            WordSeed(
                "Дубай",
                2,
                ("там всё новое и очень дорогое", "жара там — главный собеседник"),
            ),
            WordSeed(
                "Лондон",
                1,
                ("погода там — вечная тема разговора", "там ездят по другой стороне"),
            ),
            WordSeed(
                "Рим",
                2,
                ("там на каждом шагу что-то древнее", "туда едут смотреть и есть одновременно"),
            ),
            WordSeed(
                "Стамбул",
                3,
                ("он стоит сразу на двух сторонах", "там принято торговаться"),
            ),
            WordSeed(
                "Рио-де-Жанейро",
                3,
                ("главный праздник там длится несколько дней", "океан и горы там в одном кадре"),
            ),
        ),
    ),
    CategorySeed(
        slug="food",
        title="Еда",
        words=(
            WordSeed(
                "пицца",
                1,
                (
                    "это обычно делят на всех",
                    "это заказывают, когда лень готовить",
                    "круглая форма этому не мешает",
                ),
            ),
            WordSeed(
                "борщ",
                1,
                ("у каждой семьи свой правильный рецепт", "на второй день бывает даже лучше"),
            ),
            WordSeed(
                "суши",
                2,
                ("это едят маленькими порциями", "к этому подают что-то очень острое"),
            ),
            WordSeed(
                "мороженое",
                1,
                ("с этим лучше не тянуть", "этим подкупают детей"),
            ),
            WordSeed(
                "шаурма",
                2,
                ("это берут на ходу", "качество сильнее обычного зависит от места"),
            ),
            WordSeed(
                "блины",
                2,
                ("в честь этого есть целая неделя", "к этому подходит и сладкое, и солёное"),
            ),
            WordSeed(
                "оливье",
                3,
                ("без этого не обходится один вечер в году", "это делают сразу большим тазом"),
            ),
            WordSeed(
                "попкорн",
                2,
                ("это едят, глядя в другую сторону", "это заметно шумит"),
            ),
            WordSeed(
                "шашлык",
                2,
                ("ради этого выезжают за город", "вокруг этого всегда спорят, кто главный"),
            ),
        ),
    ),
    CategorySeed(
        slug="professions",
        title="Профессии",
        words=(
            WordSeed(
                "врач",
                1,
                ("к ним идут, когда тянуть уже нельзя", "их почерк — отдельная легенда"),
            ),
            WordSeed(
                "учитель",
                1,
                ("их помнят по имени и через двадцать лет", "работа продолжается дома вечером"),
            ),
            WordSeed(
                "программист",
                2,
                (
                    "многие делают это из дома",
                    "объяснить родителям, чем занимаются, до сих пор сложно",
                ),
            ),
            WordSeed(
                "повар",
                1,
                ("результат работы исчезает за десять минут", "работают, когда другие отдыхают"),
            ),
            WordSeed(
                "пожарный",
                2,
                ("их ждут, но лучше бы не пришлось", "форма у них очень узнаваемая"),
            ),
            WordSeed(
                "пилот",
                2,
                ("работа сбивает часовые пояса", "им доверяют больше, чем себе"),
            ),
            WordSeed(
                "парикмахер",
                2,
                ("разговор там иногда важнее результата", "результат сразу виден всем"),
            ),
            WordSeed(
                "полицейский",
                2,
                ("их появление редко радует", "работают сменами и по ночам"),
            ),
            WordSeed(
                "фотограф",
                3,
                ("просит подождать и не двигаться", "лучшее время работы — рассвет и закат"),
            ),
        ),
    ),
)


async def seed_words(session: AsyncSession) -> SeedReport:
    category_ids = await _upsert_categories(session)
    word_ids = await _upsert_words(session, category_ids)
    hints = await _upsert_hints(session, category_ids, word_ids)
    await session.commit()
    return SeedReport(categories=len(category_ids), words=len(word_ids), hints=hints)


async def _upsert_categories(session: AsyncSession) -> dict[str, int]:
    statement = insert(Category).values(
        [{"slug": category.slug, "title": category.title} for category in CATALOG]
    )
    upsert = statement.on_conflict_do_update(
        index_elements=["slug"],
        set_={"title": statement.excluded.title},
    ).returning(Category.slug, Category.id)
    return {row.slug: row.id for row in await session.execute(upsert)}


async def _upsert_words(
    session: AsyncSession, category_ids: dict[str, int]
) -> dict[tuple[int, str], int]:
    statement = insert(Word).values(
        [
            {
                "category_id": category_ids[category.slug],
                "text": word.text,
                "difficulty": word.difficulty,
            }
            for category in CATALOG
            for word in category.words
        ]
    )
    upsert = statement.on_conflict_do_update(
        index_elements=["category_id", "text"],
        set_={"difficulty": statement.excluded.difficulty},
    ).returning(Word.category_id, Word.text, Word.id)
    return {(row.category_id, row.text): row.id for row in await session.execute(upsert)}


async def _upsert_hints(
    session: AsyncSession,
    category_ids: dict[str, int],
    word_ids: dict[tuple[int, str], int],
) -> int:
    values = [
        {"word_id": word_ids[(category_ids[category.slug], word.text)], "hint_text": hint}
        for category in CATALOG
        for word in category.words
        for hint in word.hints
    ]
    await session.execute(
        insert(SpyHint)
        .values(values)
        .on_conflict_do_nothing(index_elements=["word_id", "hint_text"])
    )
    return len(values)


def main() -> None:
    configure_logging(DEFAULT_LEVEL)
    try:
        asyncio.run(_run())
    except ConfigurationError as error:
        logger.error("Сидинг невозможен: %s", error)
        raise SystemExit(1) from None


async def _run() -> None:
    settings = load_settings()
    engine = create_engine(settings)
    try:
        async with create_sessionmaker(engine)() as session:
            report = await seed_words(session)
    finally:
        await engine.dispose()

    logger.info(
        "Словарь актуален: категорий %d, слов %d, подсказок %d",
        report.categories,
        report.words,
        report.hints,
    )


if __name__ == "__main__":
    main()
