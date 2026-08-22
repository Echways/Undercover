# Групповой режим Undercover: план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** научить бота второму режиму — лобби в группе, раздача ролей каждому в личку по deep-link — и добавить таймер хода с живым отсчётом и автопереходом.

**Architecture:** лобби живёт отдельной моделью в своём ключе Redis и превращается в `GameSessionState` только в момент старта, через существующий `create_session()`. Ветвление по режиму собрано в одну функцию `board_for(state)`, которая выдаёт стратегию отрисовки: hot-seat правит одно сообщение, группа замораживает ход и шлёт новое. Таймер — задача-будильник на партию; корректность держится на сверке `(session_id, round, cursor)` и внутрипроцессных блокировках, а не на механизме сна.

**Tech Stack:** Python 3.13+, aiogram 3.30, aiogram-dialog 2.6, pydantic 2.13, redis 7.4 (asyncio), SQLAlchemy 2.0, Pillow 12, pytest 9 + pytest-asyncio.

**Spec:** `docs/superpowers/specs/2026-08-22-group-mode-design.md`

## Global Constraints

- **Ноль комментариев и ноль докстрингов** в `src/`, `tests/`, `tools/`, `scripts/`. Имена несут смысл; то, что должно пережить код, идёт в README. Исключения — `.env.example` и модульный докстринг `migrations/versions/*.py`.
- **Бренд всегда латиницей — `Undercover`.** Никаких «Шпион» и «Андеркавер» в пользовательских текстах, README и именах модулей.
- **Полная типизация**, `mypy --strict` без ошибок. `Any` — только там, где иначе нельзя.
- **SOLID / DRY / KISS / YAGNI.** Не строить «на будущее»: в задаче реализуется ровно то, что она объявляет.
- **Тексты кнопок в общем стиле проекта**: без эмодзи, короткая фраза обычным предложением, обращение на «вы». Существующие константы `Buttons` переиспользуются, а не дублируются синонимами.
- **Формулировки безличные там, где имя пришло из Telegram** — род игрока неизвестен, «высказался/высказалась» угадывать нечем.
- **Коммиты не делаются.** Владелец репозитория коммитит сам; задача считается сделанной по зелёным проверкам.
- Каждая задача заканчивается прогоном `poetry run ruff check . && poetry run ruff format --check . && poetry run mypy && poetry run pytest -m "not integration"`.
- Порог покрытия CI: 90% строк, 85% ветвей.

**Отклонения от спека, принятые на этапе планирования** (спек не переписывается, отклонения зафиксированы здесь):

1. `LobbyRepository` обходится **одним** ключом `lobby:<chat_id>`. Спек §3.5 предлагал ещё `chat_active_lobby:<chat_id>` и Lua-скрипт на снятие — они нужны `GameStateRepository`, потому что там сессия ключуется по UUID. При ключевании по `chat_id` второй ключ был бы копией первого.
2. `turn_seconds`, `turn_deadline`, `TURN_CHOICES`, `DEFAULT_TURN_SECONDS` и кнопка «Ход: …» появляются **только в фазе 2**. Спек §3.1–3.2 показывал их в разделе модели, но §13 относит к фазе 2; иначе фаза 1 привезла бы поле и кнопку, которыми никто не пользуется.
3. Добавлена `unique_name()` — спек не покрыл случай двух игроков с одинаковым именем в Telegram. В hot-seat дубликаты запрещены (`Setup.DUPLICATE_NAME`), потому что одинаковые имена на карточках не различить; в группе имя не выбирают, поэтому его разводит бот.
4. `show_or_resend_text` возвращает `int` (`message_id`), а не `Message` — вызывающему нужен только он, и это позволяет корректно обработать `message is not modified`.
5. `create_session` получает ещё и параметр `mode`, а не мутируется после вызова, — у поля один писатель.

---

# Фаза 1. Лобби и раздача ролей в личку

## Task 1: Модель лобби и её правила

**Files:**
- Modify: `src/undercover/game/models.py`
- Create: `src/undercover/game/lobby.py`
- Test: `tests/test_lobby_rules.py` (create), `tests/test_game_models.py` (modify)

**Interfaces:**
- Consumes: `undercover.game.engine.MAX_PLAYERS`, `MIN_PLAYERS`, `GameRulesError`, `max_spies_count`
- Produces:
  - `GameMode(StrEnum)` — `HOT_SEAT`, `GROUP`
  - `LobbyView(StrEnum)` — `ROSTER`, `CATEGORIES`
  - `LobbyPlayer(BaseModel)` — `user_id: int`, `name: str`
  - `LobbyState(BaseModel)` — `chat_id`, `host_user_id`, `message_id`, `players`, `spies_count`, `category_ids`, `view`, `created_at`; метод `index_of(user_id: int) -> int | None`
  - `PlayerState.user_id: int | None`
  - `GameSessionState.mode: GameMode`
  - `undercover.game.lobby`: `join(lobby, player) -> None`, `leave(lobby, user_id) -> None`, `cycle_spies_count(lobby) -> None`, `toggle_category(lobby, category_id) -> None`, `ensure_playable(lobby) -> None`, `unique_name(base: str, taken: Iterable[str]) -> str`

- [x] **Step 1: Написать падающие тесты правил лобби**

Создать `tests/test_lobby_rules.py`:

```python
import pytest

from undercover.game.engine import MAX_PLAYERS, MIN_PLAYERS, GameRulesError, max_spies_count
from undercover.game.lobby import (
    cycle_spies_count,
    ensure_playable,
    join,
    leave,
    toggle_category,
    unique_name,
)
from undercover.game.models import LobbyPlayer, LobbyState

CHAT_ID = -1001234567890
HOST_ID = 777


def lobby(players: int = 0) -> LobbyState:
    state = LobbyState(chat_id=CHAT_ID, host_user_id=HOST_ID)
    for number in range(players):
        join(state, LobbyPlayer(user_id=HOST_ID + number, name=f"Игрок-{number}"))
    return state


def test_join_appends_in_arrival_order() -> None:
    state = lobby()

    join(state, LobbyPlayer(user_id=1, name="Аня"))
    join(state, LobbyPlayer(user_id=2, name="Борис"))

    assert [player.name for player in state.players] == ["Аня", "Борис"]


def test_join_refuses_the_same_user_twice() -> None:
    state = lobby()
    join(state, LobbyPlayer(user_id=1, name="Аня"))

    with pytest.raises(GameRulesError):
        join(state, LobbyPlayer(user_id=1, name="Аня"))


def test_join_refuses_the_seventeenth_player() -> None:
    state = lobby(MAX_PLAYERS)

    with pytest.raises(GameRulesError):
        join(state, LobbyPlayer(user_id=-1, name="Лишний"))


def test_leave_removes_the_player_and_keeps_the_rest_in_order() -> None:
    state = lobby(3)

    leave(state, state.players[1].user_id)

    assert [player.name for player in state.players] == ["Игрок-0", "Игрок-2"]


def test_leave_refuses_a_stranger() -> None:
    state = lobby(2)

    with pytest.raises(GameRulesError):
        leave(state, user_id=-1)


def test_leave_clamps_spies_down_to_what_the_smaller_table_allows() -> None:
    state = lobby(6)
    cycle_spies_count(state)

    assert state.spies_count == max_spies_count(6)

    leave(state, state.players[0].user_id)

    assert state.spies_count == max_spies_count(5)


def test_spies_cycle_wraps_at_the_limit() -> None:
    state = lobby(6)
    seen = []
    for _ in range(3):
        cycle_spies_count(state)
        seen.append(state.spies_count)

    assert seen == [2, 1, 2]


def test_spies_cycle_stays_at_one_when_the_table_allows_only_one() -> None:
    state = lobby(MIN_PLAYERS)

    cycle_spies_count(state)

    assert state.spies_count == 1


def test_toggle_category_adds_then_removes() -> None:
    state = lobby()

    toggle_category(state, 7)
    assert state.category_ids == [7]

    toggle_category(state, 7)
    assert state.category_ids == []


def test_ensure_playable_refuses_a_table_of_one() -> None:
    state = lobby(1)

    with pytest.raises(GameRulesError):
        ensure_playable(state)


def test_ensure_playable_passes_the_minimum_table() -> None:
    ensure_playable(lobby(MIN_PLAYERS))


def test_unique_name_leaves_a_free_name_alone() -> None:
    assert unique_name("Аня", taken=["Борис"]) == "Аня"


def test_unique_name_numbers_the_collisions() -> None:
    assert unique_name("Аня", taken=["Аня"]) == "Аня 2"
    assert unique_name("Аня", taken=["Аня", "Аня 2"]) == "Аня 3"


def test_unique_name_keeps_the_result_short_enough_for_a_card() -> None:
    from undercover.game.engine import MAX_NAME_LENGTH

    long_name = "Ы" * MAX_NAME_LENGTH
    result = unique_name(long_name, taken=[long_name])

    assert len(result) <= MAX_NAME_LENGTH
    assert result != long_name
```

- [x] **Step 2: Убедиться, что тесты падают**

Run: `poetry run pytest tests/test_lobby_rules.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'undercover.game.lobby'`

- [x] **Step 3: Дополнить `game/models.py`**

Добавить в файл (`GameMode` рядом с `Role`, лоббийные модели — после `GameSessionState`):

```python
class GameMode(StrEnum):
    HOT_SEAT = "hot_seat"
    GROUP = "group"


class LobbyView(StrEnum):
    ROSTER = "roster"
    CATEGORIES = "categories"


class LobbyPlayer(BaseModel):
    user_id: int
    name: str


class LobbyState(BaseModel):
    chat_id: int
    host_user_id: int

    message_id: int | None = None

    players: list[LobbyPlayer] = Field(default_factory=list)

    spies_count: int = Field(default=1, ge=1)

    category_ids: list[int] = Field(default_factory=list)

    view: LobbyView = LobbyView.ROSTER

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def index_of(self, user_id: int) -> int | None:
        return next(
            (index for index, player in enumerate(self.players) if player.user_id == user_id),
            None,
        )
```

В `PlayerState` добавить поле после `card_file_id`:

```python
    user_id: int | None = None
```

В `GameSessionState` добавить поле после `host_user_id`:

```python
    mode: GameMode = GameMode.HOT_SEAT
```

Умолчания подобраны так, что сессии, уже лежащие в Redis, читаются без миграции.

- [x] **Step 4: Создать `game/lobby.py`**

```python
from collections.abc import Iterable

from undercover.game.engine import (
    MAX_NAME_LENGTH,
    MAX_PLAYERS,
    MIN_PLAYERS,
    GameRulesError,
    max_spies_count,
)
from undercover.game.models import LobbyPlayer, LobbyState


def join(lobby: LobbyState, player: LobbyPlayer) -> None:
    if lobby.index_of(player.user_id) is not None:
        raise GameRulesError(f"{player.name} уже в составе")
    if len(lobby.players) >= MAX_PLAYERS:
        raise GameRulesError(f"в составе уже {MAX_PLAYERS} игроков — больше не поместится")
    lobby.players.append(player)


def leave(lobby: LobbyState, user_id: int) -> None:
    index = lobby.index_of(user_id)
    if index is None:
        raise GameRulesError("этого игрока нет в составе")
    del lobby.players[index]
    _clamp_spies(lobby)


def cycle_spies_count(lobby: LobbyState) -> None:
    lobby.spies_count = lobby.spies_count % _spies_limit(lobby) + 1


def toggle_category(lobby: LobbyState, category_id: int) -> None:
    if category_id in lobby.category_ids:
        lobby.category_ids.remove(category_id)
    else:
        lobby.category_ids.append(category_id)


def ensure_playable(lobby: LobbyState) -> None:
    if len(lobby.players) < MIN_PLAYERS:
        raise GameRulesError(f"для партии нужно хотя бы {MIN_PLAYERS} игрока")
    _clamp_spies(lobby)


def unique_name(base: str, taken: Iterable[str]) -> str:
    reserved = set(taken)
    trimmed = base[:MAX_NAME_LENGTH]
    if trimmed not in reserved:
        return trimmed

    for number in range(2, MAX_PLAYERS + 2):
        suffix = f" {number}"
        candidate = f"{base[: MAX_NAME_LENGTH - len(suffix)]}{suffix}"
        if candidate not in reserved:
            return candidate

    raise GameRulesError(f"не удалось развести имя «{base}»")


def _spies_limit(lobby: LobbyState) -> int:
    return max_spies_count(len(lobby.players)) if lobby.players else 1


def _clamp_spies(lobby: LobbyState) -> None:
    lobby.spies_count = min(lobby.spies_count, _spies_limit(lobby))
```

- [x] **Step 5: Дополнить `tests/test_game_models.py`**

```python
def test_lobby_finds_a_player_by_telegram_id_and_misses_a_stranger() -> None:
    lobby = LobbyState(
        chat_id=-100,
        host_user_id=1,
        players=[LobbyPlayer(user_id=1, name="Аня"), LobbyPlayer(user_id=2, name="Борис")],
    )

    assert lobby.index_of(2) == 1
    assert lobby.index_of(99) is None


def test_old_sessions_without_the_new_fields_still_read_as_hot_seat() -> None:
    raw = (
        '{"session_id": "s", "chat_id": -100, "host_user_id": 1, "status": "discussion",'
        ' "players": [{"order_index": 0, "name": "Аня", "is_spy": false}],'
        ' "word_id": 1, "word_text": "пицца"}'
    )

    state = GameSessionState.model_validate_json(raw)

    assert state.mode is GameMode.HOT_SEAT
    assert state.players[0].user_id is None
```

- [x] **Step 6: Прогнать проверки**

Run: `poetry run ruff check . && poetry run ruff format --check . && poetry run mypy && poetry run pytest -m "not integration" -q`
Expected: PASS. `test_game_core_pulls_in_neither_telegram_nor_the_database` в `test_engine.py` должен остаться зелёным — `game/lobby.py` не тянет aiogram.

---

## Task 2: Движок принимает Telegram-идентификаторы

**Files:**
- Modify: `src/undercover/game/engine.py:45-62`, `src/undercover/game/engine.py:110-132`
- Test: `tests/test_engine.py` (modify)

**Interfaces:**
- Consumes: `GameMode`, `PlayerState.user_id` из Task 1
- Produces:
  - `assign_roles(player_names, spies_count, rng, player_ids: Sequence[int] | None = None) -> list[PlayerState]`
  - `create_session(*, chat_id, host_user_id, player_names, spies_count, words, rng, category_ids=None, player_ids: Sequence[int] | None = None, mode: GameMode = GameMode.HOT_SEAT) -> GameSessionState`

- [x] **Step 1: Написать падающие тесты**

Добавить в `tests/test_engine.py`:

```python
def test_player_ids_land_on_the_players_in_the_same_order() -> None:
    players = assign_roles(
        ["Аня", "Боря", "Вера"], spies_count=1, rng=rng(), player_ids=[10, 20, 30]
    )

    assert [player.user_id for player in players] == [10, 20, 30]


def test_players_have_no_telegram_id_when_none_were_given() -> None:
    players = assign_roles(["Аня", "Боря"], spies_count=1, rng=rng())

    assert [player.user_id for player in players] == [None, None]


def test_a_short_list_of_ids_is_a_rules_error() -> None:
    with pytest.raises(GameRulesError):
        assign_roles(["Аня", "Боря"], spies_count=1, rng=rng(), player_ids=[10])


async def test_create_session_carries_mode_and_ids_through() -> None:
    state = await create_session(
        chat_id=-100,
        host_user_id=1,
        player_names=["Аня", "Боря"],
        player_ids=[10, 20],
        spies_count=1,
        words=FakeWordsSource(),
        rng=rng(),
        mode=GameMode.GROUP,
    )

    assert state.mode is GameMode.GROUP
    assert [player.user_id for player in state.players] == [10, 20]
```

`FakeWordsSource` — уже существующий в файле фейк источника слов; если его имя другое, взять то, что используют соседние тесты `create_session`.

- [x] **Step 2: Убедиться, что тесты падают**

Run: `poetry run pytest tests/test_engine.py -q -k "player_ids or mode or telegram_id"`
Expected: FAIL — `TypeError: assign_roles() got an unexpected keyword argument 'player_ids'`

- [x] **Step 3: Заменить `assign_roles`**

```python
def assign_roles(
    player_names: Sequence[str],
    spies_count: int,
    rng: Random,
    player_ids: Sequence[int] | None = None,
) -> list[PlayerState]:
    players_count = len(player_names)
    if not MIN_PLAYERS <= players_count <= MAX_PLAYERS:
        raise GameRulesError(
            f"игроков должно быть от {MIN_PLAYERS} до {MAX_PLAYERS}, а не {players_count}"
        )

    ids: tuple[int | None, ...] = (
        tuple(player_ids) if player_ids is not None else (None,) * players_count
    )
    if len(ids) != players_count:
        raise GameRulesError(
            f"идентификаторов {len(ids)}, а игроков {players_count} — состав не сходится"
        )

    limit = max_spies_count(players_count)
    if not 1 <= spies_count <= limit:
        raise GameRulesError(
            f"шпионов на {players_count} игроков должно быть от 1 до {limit}, а не {spies_count}"
        )

    spies = set(rng.sample(range(players_count), spies_count))
    return [
        PlayerState(
            order_index=order_index,
            name=name,
            is_spy=order_index in spies,
            user_id=ids[order_index],
        )
        for order_index, name in enumerate(player_names)
    ]
```

- [x] **Step 4: Заменить `create_session`**

```python
async def create_session(
    *,
    chat_id: int,
    host_user_id: int,
    player_names: Sequence[str],
    spies_count: int,
    words: WordsSource,
    rng: Random,
    category_ids: Sequence[int] | None = None,
    player_ids: Sequence[int] | None = None,
    mode: GameMode = GameMode.HOT_SEAT,
) -> GameSessionState:
    players = assign_roles(player_names, spies_count, rng, player_ids)
    word = await pick_word(words, category_ids, rng)
    return GameSessionState(
        session_id=str(UUID(int=rng.getrandbits(128), version=4)),
        chat_id=chat_id,
        host_user_id=host_user_id,
        mode=mode,
        status=GameStatus.SETUP,
        players=players,
        word_id=word.word_id,
        word_text=word.text,
        category_ids=list(category_ids or ()),
        hint_by_spy=assign_hints(players, word, rng),
    )
```

Импорт `GameMode` добавить в строку импорта из `undercover.game.models`.

- [x] **Step 5: Прогнать проверки**

Run: `poetry run ruff check . && poetry run mypy && poetry run pytest -m "not integration" -q`
Expected: PASS

---

## Task 3: Репозиторий лобби

**Files:**
- Create: `src/undercover/redis/lobby_state.py`
- Modify: `src/undercover/di.py:22-66`
- Create: `tests/fake_lobbies.py`
- Test: `tests/test_lobby_repository.py` (create), `tests/test_di.py` (modify)

**Interfaces:**
- Consumes: `LobbyState` из Task 1
- Produces:
  - `LobbyRepository(redis: Redis, ttl: timedelta = LOBBY_TTL)` с `save(lobby) -> None`, `load(chat_id) -> LobbyState | None`, `delete(chat_id) -> None`
  - `LOBBY_TTL`, `LOBBY_KEY_PREFIX`
  - `AppDependencies.lobbies: LobbyRepository`, попадает в `as_workflow_data()` под ключом `lobbies`
  - `tests/fake_lobbies.py`: `FakeLobbyRepository(*lobbies)` со свойством `stored`

- [x] **Step 1: Написать падающие тесты**

Создать `tests/test_lobby_repository.py`:

```python
import pytest
from redis.asyncio import Redis

from undercover.game.models import LobbyPlayer, LobbyState, LobbyView
from undercover.redis.lobby_state import LOBBY_KEY_PREFIX, LobbyRepository

pytestmark = pytest.mark.integration

CHAT_ID = -1001234567890


def lobby() -> LobbyState:
    return LobbyState(
        chat_id=CHAT_ID,
        host_user_id=777,
        message_id=42,
        players=[LobbyPlayer(user_id=1, name="Аня")],
        spies_count=1,
        category_ids=[7],
        view=LobbyView.CATEGORIES,
    )


async def test_saved_lobby_reads_back_field_for_field(redis_client: Redis) -> None:
    repository = LobbyRepository(redis_client)
    await repository.save(lobby())

    loaded = await repository.load(CHAT_ID)

    assert loaded == lobby()


async def test_missing_lobby_is_none(redis_client: Redis) -> None:
    assert await LobbyRepository(redis_client).load(CHAT_ID) is None


async def test_delete_removes_the_lobby(redis_client: Redis) -> None:
    repository = LobbyRepository(redis_client)
    await repository.save(lobby())

    await repository.delete(CHAT_ID)

    assert await repository.load(CHAT_ID) is None


async def test_lobby_key_expires_so_a_forgotten_lobby_does_not_linger(
    redis_client: Redis,
) -> None:
    await LobbyRepository(redis_client).save(lobby())

    assert await redis_client.ttl(f"{LOBBY_KEY_PREFIX}{CHAT_ID}") > 0
```

- [x] **Step 2: Убедиться, что тесты падают**

Run: `poetry run pytest tests/test_lobby_repository.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'undercover.redis.lobby_state'` (либо skip, если Docker недоступен — тогда прогонять с Docker)

- [x] **Step 3: Создать `redis/lobby_state.py`**

```python
from datetime import timedelta
from typing import Final

from redis.asyncio import Redis

from undercover.game.models import LobbyState

__all__ = ["LOBBY_KEY_PREFIX", "LOBBY_TTL", "LobbyRepository", "LobbyState"]

LOBBY_TTL: Final = timedelta(hours=6)

LOBBY_KEY_PREFIX: Final = "lobby:"


class LobbyRepository:
    def __init__(self, redis: Redis, ttl: timedelta = LOBBY_TTL) -> None:
        self._redis = redis
        self._ttl = ttl

    async def save(self, lobby: LobbyState) -> None:
        await self._redis.set(_lobby_key(lobby.chat_id), lobby.model_dump_json(), ex=self._ttl)

    async def load(self, chat_id: int) -> LobbyState | None:
        raw = await self._redis.get(_lobby_key(chat_id))
        return None if raw is None else LobbyState.model_validate_json(raw)

    async def delete(self, chat_id: int) -> None:
        await self._redis.delete(_lobby_key(chat_id))


def _lobby_key(chat_id: int) -> str:
    return f"{LOBBY_KEY_PREFIX}{chat_id}"
```

Второго ключа-маркера здесь нет намеренно: лобби ключуется по чату, так что `lobby:<chat_id>` сам себе маркер активности.

- [x] **Step 4: Подключить к `di.py`**

В `AppDependencies` добавить поле после `games`:

```python
    lobbies: LobbyRepository
```

В `as_workflow_data()` добавить строку:

```python
            "lobbies": self.lobbies,
```

В `build_dependencies` добавить в конструктор:

```python
        lobbies=LobbyRepository(redis),
```

И импорт: `from undercover.redis.lobby_state import LobbyRepository`.

- [x] **Step 5: Создать `tests/fake_lobbies.py`**

```python
from undercover.game.models import LobbyState
from undercover.redis.lobby_state import LobbyRepository


class FakeLobbyRepository(LobbyRepository):
    def __init__(self, *lobbies: LobbyState) -> None:
        self._lobbies = {lobby.chat_id: lobby.model_copy(deep=True) for lobby in lobbies}
        self.saves = 0

    async def load(self, chat_id: int) -> LobbyState | None:
        lobby = self._lobbies.get(chat_id)
        return None if lobby is None else lobby.model_copy(deep=True)

    async def save(self, lobby: LobbyState) -> None:
        self._lobbies[lobby.chat_id] = lobby.model_copy(deep=True)
        self.saves += 1

    async def delete(self, chat_id: int) -> None:
        self._lobbies.pop(chat_id, None)

    @property
    def stored(self) -> LobbyState:
        (lobby,) = self._lobbies.values()
        return lobby

    @property
    def is_empty(self) -> bool:
        return not self._lobbies
```

- [x] **Step 6: Дополнить `tests/test_di.py`**

Найти тест, проверяющий состав `as_workflow_data()`, и добавить `"lobbies"` в ожидаемый набор ключей. Если такого теста нет — добавить:

```python
def test_workflow_data_carries_both_repositories(set_env: SetEnv) -> None:
    set_env()
    dependencies = build_dependencies(load_settings())

    assert {"games", "lobbies"} <= set(dependencies.as_workflow_data())
```

- [x] **Step 7: Прогнать проверки**

Run: `poetry run ruff check . && poetry run mypy && poetry run pytest -q` (с Docker — интеграционные тесты нужны)
Expected: PASS

---

## Task 4: Текстовое сообщение, которое переживает удаление

**Files:**
- Modify: `src/undercover/bot/message_utils.py`
- Test: `tests/test_message_utils.py` (modify)

**Interfaces:**
- Produces: `show_or_resend_text(bot, chat_id, message_id: int | None, text: str, keyboard: InlineKeyboardMarkup | None = None) -> int`

- [x] **Step 1: Написать падающие тесты**

Добавить в `tests/test_message_utils.py`:

```python
from aiogram.methods import EditMessageText, SendMessage

from undercover.bot.message_utils import show_or_resend_text


async def test_first_call_sends_and_returns_the_new_message_id() -> None:
    session = FakeSession()
    bot = make_bot(session)

    message_id = await show_or_resend_text(bot, CHAT_ID, None, "Набор в партию")

    assert session.calls(SendMessage)
    assert message_id == SENT_MESSAGE_ID


async def test_later_calls_edit_in_place_and_keep_the_message_id() -> None:
    session = FakeSession()
    bot = make_bot(session)

    message_id = await show_or_resend_text(bot, CHAT_ID, 500, "Набор в партию")

    assert session.calls(EditMessageText)
    assert not session.calls(SendMessage)
    assert message_id == 500


async def test_a_deleted_message_is_replaced_by_a_fresh_one() -> None:
    session = FakeSession()
    session.failures[EditMessageText] = TelegramBadRequest(
        method=EditMessageText(text="x"), message="message to edit not found"
    )
    bot = make_bot(session)

    message_id = await show_or_resend_text(bot, CHAT_ID, 500, "Набор в партию")

    assert session.calls(SendMessage)
    assert message_id == SENT_MESSAGE_ID


async def test_an_unchanged_roster_does_not_produce_a_duplicate_message() -> None:
    session = FakeSession()
    session.failures[EditMessageText] = TelegramBadRequest(
        method=EditMessageText(text="x"),
        message="Bad Request: message is not modified",
    )
    bot = make_bot(session)

    message_id = await show_or_resend_text(bot, CHAT_ID, 500, "Набор в партию")

    assert not session.calls(SendMessage)
    assert message_id == 500
```

Импорты `CHAT_ID`, `SENT_MESSAGE_ID`, `FakeSession`, `make_bot` — из `fake_bot`; `TelegramBadRequest` — из `aiogram.exceptions`.

- [x] **Step 2: Научить `FakeSession` отвечать на `EditMessageText`**

В `tests/fake_bot.py` добавить `EditMessageText` в импорт из `aiogram.methods` и в `_default_result`:

```python
        if isinstance(method, EditMessageText):
            assert method.message_id is not None
            return text_message(method.message_id, method.text)
```

- [x] **Step 3: Убедиться, что тесты падают**

Run: `poetry run pytest tests/test_message_utils.py -q`
Expected: FAIL — `ImportError: cannot import name 'show_or_resend_text'`

- [x] **Step 4: Реализовать**

Добавить в `src/undercover/bot/message_utils.py`:

```python
NOT_MODIFIED: Final = "message is not modified"


async def show_or_resend_text(
    bot: Bot,
    chat_id: int,
    message_id: int | None,
    text: str,
    keyboard: InlineKeyboardMarkup | None = None,
) -> int:
    if message_id is not None:
        try:
            await bot.edit_message_text(
                text, chat_id=chat_id, message_id=message_id, reply_markup=keyboard
            )
        except TelegramBadRequest as error:
            if NOT_MODIFIED in str(error):
                return message_id
            logger.info("правка текста %s не удалась (%s), шлём новое", message_id, error)
        else:
            return message_id

    sent = await bot.send_message(chat_id, text, reply_markup=keyboard)
    return sent.message_id
```

Добавить `Final` в импорт из `typing`.

- [x] **Step 5: Прогнать проверки**

Run: `poetry run ruff check . && poetry run mypy && poetry run pytest -m "not integration" -q`
Expected: PASS

---

## Task 5: Раздача ролей в личку

**Files:**
- Create: `src/undercover/bot/role_delivery.py`
- Modify: `src/undercover/bot/routers/reveal.py:175-178` (убрать `_render_role_card`, импортировать `render_role_card`)
- Modify: `src/undercover/texts.py`
- Test: `tests/test_role_delivery.py` (create)

**Interfaces:**
- Consumes: `GameSessionState`, `PlayerState`, `as_photo`, `render_civilian_card`, `render_spy_card`, `CARD_SUFFIX`
- Produces:
  - `render_role_card(player: PlayerState, state: GameSessionState) -> bytes`
  - `deliver_roles(bot: Bot, state: GameSessionState) -> list[PlayerState]` — возвращает тех, кому не дошло
  - `texts.Delivery.ROLE_CAPTION`

- [x] **Step 1: Написать падающие тесты**

Создать `tests/test_role_delivery.py`:

```python
from typing import Final

import pytest
from aiogram.exceptions import TelegramForbiddenError
from aiogram.methods import SendPhoto

from fake_bot import CHAT_ID, HOST_ID, FakeSession, make_bot
from fake_words import WORD
from undercover.bot.role_delivery import deliver_roles, render_role_card
from undercover.game.models import GameMode, GameSessionState, GameStatus, PlayerState

SESSION_ID: Final = "11111111-1111-1111-1111-111111111111"
HINT: Final = "её режут на куски"


def make_state(*, ids: tuple[int | None, ...] = (10, 20, 30)) -> GameSessionState:
    return GameSessionState(
        session_id=SESSION_ID,
        chat_id=CHAT_ID,
        host_user_id=HOST_ID,
        mode=GameMode.GROUP,
        status=GameStatus.SETUP,
        players=[
            PlayerState(order_index=index, name=f"Игрок-{index}", is_spy=index == 1, user_id=user)
            for index, user in enumerate(ids)
        ],
        word_id=42,
        word_text=WORD,
        hint_by_spy={1: HINT},
    )


async def test_every_player_gets_a_card_in_their_own_chat() -> None:
    session = FakeSession()

    undelivered = await deliver_roles(make_bot(session), make_state())

    assert undelivered == []
    assert [call.chat_id for call in session.calls(SendPhoto)] == [10, 20, 30]


async def test_a_blocked_player_comes_back_as_undelivered() -> None:
    session = FakeSession()
    session.failures[SendPhoto] = TelegramForbiddenError(
        method=SendPhoto(chat_id=10, photo="x"), message="bot was blocked by the user"
    )

    undelivered = await deliver_roles(make_bot(session), make_state())

    assert [player.name for player in undelivered] == ["Игрок-0"]


async def test_a_player_without_a_telegram_id_is_undelivered_without_a_request() -> None:
    session = FakeSession()

    undelivered = await deliver_roles(make_bot(session), make_state(ids=(10, 20, None)))

    assert [player.name for player in undelivered] == ["Игрок-2"]
    assert len(session.calls(SendPhoto)) == 2


def test_the_spy_card_carries_the_hint_and_the_civilian_card_the_word() -> None:
    state = make_state()

    assert render_role_card(state.players[1], state) != render_role_card(state.players[0], state)
```

`FakeSession.failures` снимает исключение по первому обращению (`failures.pop`), поэтому во втором тесте падает ровно первая отправка — это и проверяется.

- [x] **Step 2: Убедиться, что тесты падают**

Run: `poetry run pytest tests/test_role_delivery.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'undercover.bot.role_delivery'`

- [x] **Step 3: Добавить текст в `texts.py`**

Рядом с классом `Reveal`:

```python
class Delivery:
    ROLE_CAPTION: Final = "Ваша карточка. Запомните и возвращайтесь в группу."
```

- [x] **Step 4: Создать `bot/role_delivery.py`**

```python
import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from undercover.bot.message_utils import as_photo
from undercover.game.models import GameSessionState, PlayerState
from undercover.media.card_renderer import (
    CARD_SUFFIX,
    render_civilian_card,
    render_spy_card,
)
from undercover.texts import Delivery

logger = logging.getLogger(__name__)


def render_role_card(player: PlayerState, state: GameSessionState) -> bytes:
    if player.is_spy:
        return render_spy_card(player.name, state.hint_by_spy[player.order_index])
    return render_civilian_card(player.name, state.word_text)


async def deliver_roles(bot: Bot, state: GameSessionState) -> list[PlayerState]:
    delivered = await asyncio.gather(
        *(_deliver_one(bot, state, player) for player in state.players)
    )
    return [
        player
        for player, reached in zip(state.players, delivered, strict=True)
        if not reached
    ]


async def _deliver_one(bot: Bot, state: GameSessionState, player: PlayerState) -> bool:
    if player.user_id is None:
        logger.warning("партия %s: у игрока %s нет личного чата", state.session_id, player.name)
        return False

    try:
        image = await asyncio.to_thread(render_role_card, player, state)
        await bot.send_photo(
            player.user_id,
            as_photo(image, f"role_{player.order_index}.{CARD_SUFFIX}"),
            caption=Delivery.ROLE_CAPTION,
        )
    except TelegramAPIError as error:
        logger.info("партия %s: роль не дошла до %s (%s)", state.session_id, player.name, error)
        return False
    return True
```

- [x] **Step 5: Убрать дубль из `reveal.py`**

Удалить приватную `_render_role_card` и заменить её вызов в `cb_show_role` на импортированную:

```python
from undercover.bot.role_delivery import render_role_card
```

и в теле `cb_show_role`: `image = await asyncio.to_thread(render_role_card, player, state)`.

Из импорта `undercover.media.card_renderer` в `reveal.py` убрать `render_civilian_card` и `render_spy_card` — там остаются только `CARD_SUFFIX` и `render_hidden_card`.

- [x] **Step 6: Прогнать проверки**

Run: `poetry run ruff check . && poetry run mypy && poetry run pytest -m "not integration" -q`
Expected: PASS, включая существующий `tests/test_reveal.py` без правок.

---

## Task 6: Доски обсуждения

**Files:**
- Create: `src/undercover/bot/boards.py`
- Test: `tests/test_boards.py` (create)

**Interfaces:**
- Consumes: `GameMode`, `GameSessionState`, `show_or_advance_card`, `Photo`
- Produces:
  - `DiscussionBoard(Protocol)` — `open_turn(bot, state, photo, caption, keyboard) -> int`, `close_turn(bot, state, caption) -> None`
  - `SingleCardBoard`, `FeedBoard`
  - `board_for(state: GameSessionState) -> DiscussionBoard`

- [x] **Step 1: Написать падающие тесты**

Создать `tests/test_boards.py`:

```python
from typing import Final

from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import EditMessageCaption, EditMessageMedia, SendPhoto
from aiogram.types import InlineKeyboardMarkup

from fake_bot import CHAT_ID, HOST_ID, FakeSession, make_bot
from undercover.bot.boards import FeedBoard, SingleCardBoard, board_for
from undercover.game.models import GameMode, GameSessionState, GameStatus, PlayerState

SESSION_ID: Final = "11111111-1111-1111-1111-111111111111"
KEYBOARD: Final = InlineKeyboardMarkup(inline_keyboard=[])


def make_state(mode: GameMode, message_id: int | None = 500) -> GameSessionState:
    return GameSessionState(
        session_id=SESSION_ID,
        chat_id=CHAT_ID,
        host_user_id=HOST_ID,
        mode=mode,
        status=GameStatus.DISCUSSION,
        players=[PlayerState(order_index=0, name="Аня", is_spy=True)],
        word_id=1,
        word_text="пицца",
        current_message_id=message_id,
    )


def test_board_is_chosen_by_the_mode_of_the_session() -> None:
    assert isinstance(board_for(make_state(GameMode.HOT_SEAT)), SingleCardBoard)
    assert isinstance(board_for(make_state(GameMode.GROUP)), FeedBoard)


async def test_hot_seat_keeps_the_whole_game_in_one_message() -> None:
    session = FakeSession()
    state = make_state(GameMode.HOT_SEAT)

    message_id = await SingleCardBoard().open_turn(
        make_bot(session), state, "photo-id", "Говорит: Аня", KEYBOARD
    )

    assert session.calls(EditMessageMedia)
    assert not session.calls(SendPhoto)
    assert message_id == 500


async def test_hot_seat_freezes_nothing_because_nothing_scrolls_away() -> None:
    session = FakeSession()

    await SingleCardBoard().close_turn(
        make_bot(session), make_state(GameMode.HOT_SEAT), "Говорит: Аня"
    )

    assert session.requests == []


async def test_the_group_gets_a_fresh_message_for_every_speaker() -> None:
    session = FakeSession()

    message_id = await FeedBoard().open_turn(
        make_bot(session), make_state(GameMode.GROUP), "photo-id", "Говорит: Аня", KEYBOARD
    )

    assert session.calls(SendPhoto)
    assert not session.calls(EditMessageMedia)
    assert message_id != 500


async def test_the_finished_turn_loses_its_buttons_and_keeps_a_report() -> None:
    session = FakeSession()

    await FeedBoard().close_turn(
        make_bot(session), make_state(GameMode.GROUP), "Говорит: Аня\nВремя вышло"
    )

    (frozen,) = session.calls(EditMessageCaption)
    assert frozen.message_id == 500
    assert frozen.caption == "Говорит: Аня\nВремя вышло"
    assert frozen.reply_markup is None


async def test_the_first_turn_of_a_group_game_has_nothing_to_freeze() -> None:
    session = FakeSession()

    await FeedBoard().close_turn(
        make_bot(session), make_state(GameMode.GROUP, message_id=None), "Говорит: Аня"
    )

    assert session.requests == []


async def test_a_deleted_turn_message_does_not_break_the_game() -> None:
    session = FakeSession()
    session.failures[EditMessageCaption] = TelegramBadRequest(
        method=EditMessageCaption(caption="x"), message="message to edit not found"
    )

    await FeedBoard().close_turn(
        make_bot(session), make_state(GameMode.GROUP), "Говорит: Аня"
    )
```

- [x] **Step 2: Научить `FakeSession` отвечать на `EditMessageCaption`**

В `tests/fake_bot.py` добавить `EditMessageCaption` в импорт и в `_default_result`:

```python
        if isinstance(method, EditMessageCaption):
            assert method.message_id is not None
            return photo_message(method.message_id)
```

- [x] **Step 3: Убедиться, что тесты падают**

Run: `poetry run pytest tests/test_boards.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'undercover.bot.boards'`

- [x] **Step 4: Создать `bot/boards.py`**

```python
import logging
from typing import Protocol

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardMarkup

from undercover.bot.message_utils import Photo, show_or_advance_card
from undercover.game.models import GameMode, GameSessionState

logger = logging.getLogger(__name__)


class DiscussionBoard(Protocol):
    async def open_turn(
        self,
        bot: Bot,
        state: GameSessionState,
        photo: Photo,
        caption: str,
        keyboard: InlineKeyboardMarkup,
    ) -> int: ...

    async def close_turn(self, bot: Bot, state: GameSessionState, caption: str) -> None: ...


class SingleCardBoard:
    async def open_turn(
        self,
        bot: Bot,
        state: GameSessionState,
        photo: Photo,
        caption: str,
        keyboard: InlineKeyboardMarkup,
    ) -> int:
        message = await show_or_advance_card(
            bot, state.chat_id, state.current_message_id, photo, caption, keyboard
        )
        return message.message_id

    async def close_turn(self, bot: Bot, state: GameSessionState, caption: str) -> None:
        return None


class FeedBoard:
    async def open_turn(
        self,
        bot: Bot,
        state: GameSessionState,
        photo: Photo,
        caption: str,
        keyboard: InlineKeyboardMarkup,
    ) -> int:
        message = await bot.send_photo(
            state.chat_id, photo, caption=caption, reply_markup=keyboard
        )
        return message.message_id

    async def close_turn(self, bot: Bot, state: GameSessionState, caption: str) -> None:
        if state.current_message_id is None:
            return
        try:
            await bot.edit_message_caption(
                chat_id=state.chat_id,
                message_id=state.current_message_id,
                caption=caption,
                reply_markup=None,
            )
        except TelegramBadRequest as error:
            logger.info("ход %s не заморозился (%s)", state.current_message_id, error)


def board_for(state: GameSessionState) -> DiscussionBoard:
    return FeedBoard() if state.mode is GameMode.GROUP else SingleCardBoard()
```

- [x] **Step 5: Прогнать проверки**

Run: `poetry run ruff check . && poetry run mypy && poetry run pytest -m "not integration" -q`
Expected: PASS

---

## Task 7: Право хода у ведущего и у говорящего

**Files:**
- Modify: `src/undercover/bot/guards.py`
- Test: `tests/test_guards.py` (create)

**Interfaces:**
- Consumes: `GameMode`, `GameSessionState`, `GameStatus`
- Produces:
  - `may_act(state: GameSessionState, user_id: int) -> bool`
  - `load_discussion(callback, session_id, games) -> GameSessionState | None`
  - `load_finished(callback, session_id, games) -> GameSessionState | None`
  - `load_game_in_phase` — прежняя сигнатура, внутри зовёт `may_act`

- [x] **Step 1: Написать падающие тесты**

Создать `tests/test_guards.py`:

```python
from typing import Final

import pytest

from fake_bot import CHAT_ID, HOST_ID
from undercover.bot.guards import may_act
from undercover.game.models import GameMode, GameSessionState, GameStatus, PlayerState

SESSION_ID: Final = "11111111-1111-1111-1111-111111111111"
SPEAKER_ID: Final = 111
BYSTANDER_ID: Final = 222


def make_state(
    mode: GameMode = GameMode.GROUP,
    status: GameStatus = GameStatus.DISCUSSION,
    **overrides: object,
) -> GameSessionState:
    defaults: dict[str, object] = {
        "session_id": SESSION_ID,
        "chat_id": CHAT_ID,
        "host_user_id": HOST_ID,
        "mode": mode,
        "status": status,
        "players": [
            PlayerState(order_index=0, name="Аня", is_spy=True, user_id=SPEAKER_ID),
            PlayerState(order_index=1, name="Борис", is_spy=False, user_id=BYSTANDER_ID),
        ],
        "word_id": 1,
        "word_text": "пицца",
        "discussion_order": [0, 1],
        "discussion_cursor": 0,
    }
    return GameSessionState.model_validate(defaults | overrides)


def test_the_host_may_always_act() -> None:
    assert may_act(make_state(), HOST_ID)
    assert may_act(make_state(GameMode.HOT_SEAT), HOST_ID)
    assert may_act(make_state(status=GameStatus.FINISHED), HOST_ID)


def test_the_current_speaker_may_end_their_own_turn() -> None:
    assert may_act(make_state(), SPEAKER_ID)


def test_a_player_waiting_for_their_turn_may_not() -> None:
    assert not may_act(make_state(), BYSTANDER_ID)


def test_the_previous_speaker_loses_the_right_when_the_turn_moves_on() -> None:
    assert not may_act(make_state(discussion_cursor=1), SPEAKER_ID)


def test_hot_seat_leaves_every_button_to_the_host() -> None:
    assert not may_act(make_state(GameMode.HOT_SEAT), SPEAKER_ID)


@pytest.mark.parametrize("status", [GameStatus.REVEAL, GameStatus.FINISHED, GameStatus.SETUP])
def test_outside_the_discussion_there_is_no_speaker(status: GameStatus) -> None:
    assert not may_act(make_state(status=status), SPEAKER_ID)


def test_a_broken_order_does_not_hand_the_buttons_to_anyone() -> None:
    assert not may_act(make_state(discussion_order=[9], discussion_cursor=0), SPEAKER_ID)
    assert not may_act(make_state(discussion_order=[], discussion_cursor=0), SPEAKER_ID)
```

- [x] **Step 2: Убедиться, что тесты падают**

Run: `poetry run pytest tests/test_guards.py -q`
Expected: FAIL — `ImportError: cannot import name 'may_act'`

- [x] **Step 3: Переписать `bot/guards.py`**

```python
from aiogram.types import CallbackQuery

from undercover.game.models import GameMode, GameSessionState, GameStatus
from undercover.redis.game_state import GameStateRepository
from undercover.texts import Discussion, Errors


def may_act(state: GameSessionState, user_id: int) -> bool:
    if user_id == state.host_user_id:
        return True
    return state.mode is GameMode.GROUP and _current_speaker_id(state) == user_id


async def load_game_in_phase(
    callback: CallbackQuery,
    session_id: str,
    games: GameStateRepository,
    expected: GameStatus,
    wrong_phase: str,
) -> GameSessionState | None:
    state = await games.load(session_id)
    if state is None:
        await callback.answer(Errors.SESSION_NOT_FOUND, show_alert=True)
        return None
    if state.status is not expected:
        await callback.answer(wrong_phase, show_alert=True)
        return None
    if not may_act(state, callback.from_user.id):
        await callback.answer(Errors.NOT_HOST, show_alert=True)
        return None
    return state


async def load_discussion(
    callback: CallbackQuery, session_id: str, games: GameStateRepository
) -> GameSessionState | None:
    return await load_game_in_phase(
        callback, session_id, games, GameStatus.DISCUSSION, Discussion.WRONG_PHASE
    )


async def load_finished(
    callback: CallbackQuery, session_id: str, games: GameStateRepository
) -> GameSessionState | None:
    return await load_game_in_phase(
        callback, session_id, games, GameStatus.FINISHED, Discussion.GAME_IS_ON
    )


def _current_speaker_id(state: GameSessionState) -> int | None:
    if state.status is not GameStatus.DISCUSSION:
        return None
    if not 0 <= state.discussion_cursor < len(state.discussion_order):
        return None
    order_index = state.discussion_order[state.discussion_cursor]
    if not 0 <= order_index < len(state.players):
        return None
    return state.players[order_index].user_id
```

- [x] **Step 4: Прогнать проверки**

Run: `poetry run ruff check . && poetry run mypy && poetry run pytest -m "not integration" -q`
Expected: PASS. `Errors.NOT_HOST` теперь показывается и участнику группы не в свой ход — текст «Партия идёт с телефона ведущего…» под это не подходит и будет переписан в Task 10.

---

## Task 8: Финальный экран уезжает в свой роутер

Чистый рефакторинг: `discussion.py` уже 313 строк и в этой фазе растёт с обеих сторон. Конец партии — самостоятельная ответственность (журнал, «Ещё партия», «Новый состав»), и живёт он отдельно.

**Files:**
- Create: `src/undercover/bot/routers/finale.py`
- Modify: `src/undercover/bot/routers/discussion.py` (убрать перенесённое)
- Modify: `src/undercover/bot/dispatcher.py:46-50`
- Test: `tests/test_finale.py` (create — перенести из `tests/test_discussion.py` тесты финала), `tests/test_discussion.py` (modify)

**Interfaces:**
- Consumes: `TalkAction`, `TalkCB` из `discussion.py`; `load_discussion`, `load_finished` из Task 7; `start_discussion` из `discussion.py`; `start_reveal` из `reveal.py`
- Produces: `create_finale_router(open_words: WordsSourceFactory, log_game: GameLogWriter) -> Router`, `FinalAction`, `FinalCB`, `GameLogWriter`

- [x] **Step 1: Создать `bot/routers/finale.py`**

Перенести из `discussion.py` без изменения поведения: `GameLogWriter`, `FinalAction`, `FinalCB`, `cb_show_spies`, `cb_play_again`, `cb_new_game`, `_write_log`, `_final_keyboard`, `_report_broken`. `_in_discussion` и `_finished_game` заменяются на `load_discussion` и `load_finished` из `guards.py`.

```python
def create_finale_router(open_words: WordsSourceFactory, log_game: GameLogWriter) -> Router:
    router = Router(name="finale")

    @router.callback_query(TalkCB.filter(F.action == TalkAction.SPIES))
    async def cb_show_spies(...) -> None: ...

    @router.callback_query(FinalCB.filter(F.action == FinalAction.AGAIN))
    async def cb_play_again(...) -> None: ...

    @router.callback_query(FinalCB.filter(F.action == FinalAction.NEW))
    async def cb_new_game(...) -> None: ...

    return router
```

Тела трёх обработчиков копируются из `discussion.py:111-201` дословно, кроме двух замен: `_in_discussion(callback, callback_data.session_id, games)` → `load_discussion(callback, callback_data.session_id, games)` и `_finished_game(...)` → `load_finished(...)`.

- [x] **Step 2: Вычистить `discussion.py`**

Убрать перенесённое. Остаются: `TalkAction`, `TalkCB`, `create_discussion_router`, `start_discussion`, `_show_speaker`, `_speaker_name`, `_round_is_over`, `_round_prefix`, `_speaker_keyboard`, `_report_broken`. `_report_broken` нужен обоим — оставить в `discussion.py` и импортировать в `finale.py`.

`create_discussion_router` теряет параметр `open_words` (он был нужен только для «Ещё партия») и становится `create_discussion_router() -> Router`. Импорты `create_session`, `EmptyWordCatalogError`, `secure_rng`, `Setup`, `StartMode`, `DialogManager`, `start_reveal`, `render_result_card` уходят в `finale.py`.

- [x] **Step 3: Перепроводить в `dispatcher.py`**

```python
    dispatcher.include_router(create_start_router())
    dispatcher.include_router(create_setup_dialog(open_words, start_reveal))
    dispatcher.include_router(create_reveal_router(start_discussion))
    dispatcher.include_router(create_discussion_router())
    dispatcher.include_router(create_finale_router(open_words, log_game))
    dispatcher.include_router(create_error_router())
```

- [x] **Step 4: Разделить тесты**

Перенести из `tests/test_discussion.py` в новый `tests/test_finale.py` все тесты, дергающие `Buttons.SHOW_SPIES`, `Buttons.PLAY_AGAIN`, `Buttons.NEW_GAME`. Фикстуру `table` и харнесс `Table`/`Card`/`cards` вынести в `tests/discussion_harness.py`, чтобы оба файла её делили, и обновить `create_discussion_router()`/`create_finale_router(...)` в сборке диспетчера внутри фикстуры.

- [x] **Step 5: Прогнать проверки**

Run: `poetry run ruff check . && poetry run mypy && poetry run pytest -m "not integration" -q`
Expected: PASS — набор тестов тот же, поведение не менялось. `wc -l src/undercover/bot/routers/discussion.py` должен показать примерно 200 строк.

---

## Task 9: Обсуждение переходит на доски

**Files:**
- Modify: `src/undercover/bot/routers/discussion.py`
- Test: `tests/test_discussion.py` (modify)

**Interfaces:**
- Consumes: `board_for` из Task 6
- Produces:
  - `speaker_caption(state: GameSessionState, cursor: int) -> str`
  - `open_turn(bot, games, state, cursor) -> None` (бывший `_show_speaker`)
  - `close_turn(bot, state) -> None`
  - `start_discussion(bot, games, state) -> None` — сигнатура прежняя

- [x] **Step 1: Написать падающие тесты**

Добавить в `tests/test_discussion.py`:

```python
async def test_a_group_game_gives_every_speaker_their_own_message(table: Table) -> None:
    state = make_state(mode=GameMode.GROUP)
    await table.games.save(state)
    await start_discussion(table.bot, table.games, state)

    first = len(table.session.calls(SendPhoto))
    await table.press(Buttons.NEXT_SPEAKER)

    assert len(table.session.calls(SendPhoto)) == first + 1
    assert not table.session.calls(EditMessageMedia)


async def test_the_finished_group_turn_is_frozen_without_buttons(table: Table) -> None:
    state = make_state(mode=GameMode.GROUP)
    await table.games.save(state)
    await start_discussion(table.bot, table.games, state)

    await table.press(Buttons.NEXT_SPEAKER)

    (frozen,) = table.session.calls(EditMessageCaption)
    assert frozen.reply_markup is None
    assert "Говорит" in (frozen.caption or "")


async def test_hot_seat_still_lives_in_one_message(table: Table) -> None:
    state = make_state()
    await table.games.save(state)
    await start_discussion(table.bot, table.games, state)

    await table.press(Buttons.NEXT_SPEAKER)

    assert not table.session.calls(EditMessageCaption)
    assert table.session.calls(EditMessageMedia)


async def test_the_speaker_may_end_their_own_turn_in_a_group(table: Table) -> None:
    state = make_state(mode=GameMode.GROUP, ids=(10, 20, 30, 40))
    await table.games.save(state)
    await start_discussion(table.bot, table.games, state)
    speaker = state.players[state.discussion_order[0]]

    await table.press(Buttons.NEXT_SPEAKER, user_id=speaker.user_id)

    assert table.games.stored.discussion_cursor == 1


async def test_a_bystander_still_cannot_move_the_turn(table: Table) -> None:
    state = make_state(mode=GameMode.GROUP, ids=(10, 20, 30, 40))
    await table.games.save(state)
    await start_discussion(table.bot, table.games, state)

    await table.press(Buttons.NEXT_SPEAKER, user_id=OUTSIDER_ID)

    assert table.games.stored.discussion_cursor == 0


async def test_a_new_round_freezes_the_last_turn_before_the_counter_moves(table: Table) -> None:
    state = make_state(mode=GameMode.GROUP, discussion_cursor=len(NAMES) - 1)
    await table.games.save(state)
    state.discussion_order = list(range(len(NAMES)))

    await table.press(Buttons.ANOTHER_ROUND)

    (frozen,) = table.session.calls(EditMessageCaption)
    assert Discussion.ROUND_PREFIX.format(round=2) not in (frozen.caption or "")
    assert table.games.stored.discussion_round == 2
```

Расширить локальную фабрику `make_state` в `tests/discussion_harness.py` параметрами `mode: GameMode = GameMode.HOT_SEAT` и `ids: tuple[int, ...] | None = None`, раскладывая `ids` по `PlayerState.user_id`.

- [x] **Step 2: Убедиться, что тесты падают**

Run: `poetry run pytest tests/test_discussion.py -q`
Expected: FAIL — группа по-прежнему правит одно сообщение, `EditMessageCaption` не вызывается

- [x] **Step 3: Заменить `_show_speaker` на пару `close_turn` / `open_turn`**

```python
def speaker_caption(state: GameSessionState, cursor: int) -> str:
    name = state.players[state.discussion_order[cursor]].name
    is_last = cursor == len(state.discussion_order) - 1
    body = (
        Discussion.LAST_TALK_CAPTION.format(name=name)
        if is_last
        else Discussion.TALK_CAPTION.format(
            position=cursor + 1, total=len(state.discussion_order), name=name
        )
    )
    return _round_prefix(state) + body


async def close_turn(bot: Bot, state: GameSessionState) -> None:
    await board_for(state).close_turn(
        bot, state, speaker_caption(state, state.discussion_cursor)
    )


async def open_turn(
    bot: Bot, games: GameStateRepository, state: GameSessionState, cursor: int
) -> None:
    name = state.players[state.discussion_order[cursor]].name
    is_last = cursor == len(state.discussion_order) - 1
    image = await asyncio.to_thread(render_speaker_card, name)

    message_id = await board_for(state).open_turn(
        bot,
        state,
        as_photo(image, f"speaker_{cursor}.{CARD_SUFFIX}"),
        speaker_caption(state, cursor),
        _speaker_keyboard(state, cursor, is_last),
    )

    state.discussion_cursor = cursor
    state.current_message_id = message_id
    await games.save(state)
```

- [x] **Step 4: Развести вызовы по обработчикам**

`start_discussion` — открывает первый ход, замораживать нечего:

```python
async def start_discussion(bot: Bot, games: GameStateRepository, state: GameSessionState) -> None:
    state.status = GameStatus.DISCUSSION
    state.discussion_order = build_discussion_order(state.players, secure_rng())
    await open_turn(bot, games, state, 0)
```

`cb_next_speaker` — заморозить текущий, открыть следующий:

```python
        await close_turn(bot, state)
        await open_turn(bot, games, state, next_cursor)
```

`cb_another_round` — заморозить **до** инкремента круга, иначе отчёт уедет в следующий круг:

```python
        await close_turn(bot, state)
        state.discussion_round += 1
        await open_turn(bot, games, state, 0)
```

- [x] **Step 5: Прогнать проверки**

Run: `poetry run ruff check . && poetry run mypy && poetry run pytest -m "not integration" -q`
Expected: PASS

---

## Task 10: Тексты лобби и его отрисовка

**Files:**
- Modify: `src/undercover/game/engine.py` (протоколы каталога переезжают сюда)
- Modify: `src/undercover/bot/routers/setup_dialog.py:43-56` (импорт вместо объявления)
- Modify: `src/undercover/texts.py`
- Create: `src/undercover/bot/lobby_view.py`
- Test: `tests/test_lobby_view.py` (create), `tests/test_texts.py` (modify)

**Interfaces:**
- Consumes: `LobbyState`, `LobbyView`, `show_or_resend_text`, `LobbyRepository`
- Produces:
  - в `game/engine.py`: `CategoryRecord(Protocol)`, `Catalog(Protocol)`, `CatalogFactory`, `WordsSourceFactory`
  - в `bot/lobby_view.py`: `LobbyAction(StrEnum)`, `LobbyCB(CallbackData, prefix="lobby")`, `JOIN_PAYLOAD_PREFIX`, `lobby_text(lobby, categories) -> str`, `lobby_keyboard(lobby, categories) -> InlineKeyboardMarkup`, `render_lobby(bot, lobbies, lobby, categories) -> None`, `join_link(bot, chat_id) -> str`
  - в `texts.py`: класс `Lobby`, новые `Buttons.JOIN_LOBBY / LEAVE_LOBBY / SPIES_COUNT`, новые `Errors.LOBBY_CLOSED / GAME_IN_CHAT / GROUP_ONLY`, переписанный `Errors.NOT_HOST`, `Start.GAME_COMMAND_DESCRIPTION`

- [x] **Step 1: Перенести протоколы каталога в движок**

Из `bot/routers/setup_dialog.py` вырезать `CategoryRecord`, `Catalog`, `CatalogFactory`, `WordsSourceFactory` и вставить в `game/engine.py` под `WordsSource`:

```python
class CategoryRecord(Protocol):
    @property
    def id(self) -> int: ...

    @property
    def title(self) -> str: ...


class Catalog(WordsSource, Protocol):
    async def list_playable_categories(self) -> Sequence[CategoryRecord]: ...


CatalogFactory = Callable[[], AbstractAsyncContextManager[Catalog]]
WordsSourceFactory = Callable[[], AbstractAsyncContextManager[WordsSource]]
```

Импорты в `engine.py`: `from collections.abc import Callable, Sequence`, `from contextlib import AbstractAsyncContextManager`. Обе — стандартная библиотека, так что `test_game_core_pulls_in_neither_telegram_nor_the_database` остаётся зелёным.

В `setup_dialog.py` и `discussion.py`/`finale.py` заменить объявления на импорт из `undercover.game.engine`.

- [x] **Step 2: Дописать тексты**

В `texts.py` добавить класс `Lobby` после `Setup`:

```python
class Lobby:
    TITLE: Final = f"{BRAND} — набор в партию."
    ROSTER: Final = "В игре ({count} из {limit}):\n{names_list}"
    EMPTY_ROSTER: Final = "Пока никого."
    SUMMARY: Final = (
        "Игроков: {players_count}, из них шпионов: {spies_count}.\nСлова: {chosen_categories}."
    )
    CALL: Final = "Жмите «Я в игре» — слово придёт в личку."

    PICK_CATEGORIES: Final = (
        "Откуда брать слово?\n\nОтметьте категории — можно несколько. Без отметок "
        "сыграем по всему словарю."
    )
    CATEGORY_CHOSEN: Final = "• {title}"
    CATEGORY_FREE: Final = "{title}"

    ALREADY_IN: Final = "Вы уже в составе."
    NOT_IN: Final = "Вас нет в составе."
    DM_WELCOME: Final = (
        "Вы в составе. Слово придёт сюда, как только ведущий начнёт партию."
    )
    STARTED: Final = "Партия началась. Роли ушли в личку."
    DELIVERY_FAILED: Final = "Роли дошли не всем — партия не началась."
    OPEN_DM: Final = (
        "Не получилось написать в личку: {names}.\nОткройте бота, нажмите «Старт» — "
        "и возвращайтесь в состав."
    )
```

В `Buttons` добавить:

```python
    JOIN_LOBBY: Final = "Я в игре"
    LEAVE_LOBBY: Final = "Выйти из состава"
    SPIES_COUNT: Final = "Шпионов: {count}"
```

В `Errors` добавить и переписать `NOT_HOST` — теперь он адресован и участнику группы, который жмёт кнопку не в свой ход:

```python
    NOT_HOST: Final = "Сейчас эта кнопка не ваша — её нажимает ведущий."
    LOBBY_CLOSED: Final = "Это лобби уже закрыто. Отправьте /game, чтобы собрать новое."
    GAME_IN_CHAT: Final = "В этом чате уже идёт партия — сначала доиграйте её."
    GROUP_ONLY: Final = "Так играют в группе: добавьте бота туда и отправьте /game."
```

В `Start` добавить:

```python
    GAME_COMMAND_DESCRIPTION: Final = "Партия в группе"
```

- [x] **Step 3: Написать падающие тесты отрисовки**

Создать `tests/test_lobby_view.py`:

```python
from typing import Final

from fake_words import catalog
from undercover.bot.lobby_view import LobbyAction, LobbyCB, lobby_keyboard, lobby_text
from undercover.game.engine import MAX_PLAYERS
from undercover.game.models import LobbyPlayer, LobbyState, LobbyView
from undercover.texts import Buttons, Lobby

CHAT_ID: Final = -1001234567890
CATALOG: Final = catalog("Еда", "Города")


def lobby(players: int = 0, **overrides: object) -> LobbyState:
    defaults: dict[str, object] = {
        "chat_id": CHAT_ID,
        "host_user_id": 777,
        "players": [
            LobbyPlayer(user_id=index, name=f"Игрок-{index}") for index in range(players)
        ],
    }
    return LobbyState.model_validate(defaults | overrides)


def texts_of(lobby_state: LobbyState) -> list[str]:
    return [
        button.text
        for row in lobby_keyboard(lobby_state, CATALOG).inline_keyboard
        for button in row
    ]


def test_an_empty_lobby_says_so_instead_of_showing_an_empty_list() -> None:
    assert Lobby.EMPTY_ROSTER in lobby_text(lobby(), CATALOG)


def test_the_roster_is_numbered_from_one_and_shows_the_ceiling() -> None:
    text = lobby_text(lobby(2), CATALOG)

    assert "1. Игрок-0" in text
    assert "2. Игрок-1" in text
    assert str(MAX_PLAYERS) in text


def test_the_summary_says_whole_dictionary_when_nothing_is_chosen() -> None:
    assert "весь словарь" in lobby_text(lobby(3), CATALOG)


def test_the_summary_lists_the_chosen_categories_by_title() -> None:
    text = lobby_text(lobby(3, category_ids=[1]), CATALOG)

    assert "Еда" in text
    assert "Города" not in text


def test_the_roster_keyboard_carries_join_leave_settings_and_start() -> None:
    assert texts_of(lobby(2)) == [
        Buttons.JOIN_LOBBY,
        Buttons.LEAVE_LOBBY,
        Buttons.SPIES_COUNT.format(count=1),
        Buttons.CHANGE_CATEGORIES,
        Buttons.PLAY,
    ]


def test_a_one_category_dictionary_offers_no_choice() -> None:
    single = [
        item.text
        for row in lobby_keyboard(lobby(2), catalog("Еда")).inline_keyboard
        for item in row
    ]

    assert Buttons.CHANGE_CATEGORIES not in single
    assert Buttons.JOIN_LOBBY in single


def test_the_category_view_marks_the_chosen_ones_and_offers_done() -> None:
    state = lobby(2, view=LobbyView.CATEGORIES, category_ids=[1])

    assert Lobby.PICK_CATEGORIES in lobby_text(state, CATALOG)
    assert texts_of(state) == [
        Lobby.CATEGORY_CHOSEN.format(title="Еда"),
        Lobby.CATEGORY_FREE.format(title="Города"),
        Buttons.CATEGORIES_DONE,
    ]


def test_callback_data_fits_telegram_limit() -> None:
    packed = LobbyCB(action=LobbyAction.CATEGORY, value=999999).pack()

    assert len(packed.encode()) <= 64
```

- [x] **Step 4: Убедиться, что тесты падают**

Run: `poetry run pytest tests/test_lobby_view.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'undercover.bot.lobby_view'`

- [x] **Step 5: Создать `bot/lobby_view.py`**

```python
from collections.abc import Sequence
from enum import StrEnum
from typing import Final

from aiogram import Bot
from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.deep_linking import create_start_link

from undercover.bot.keyboards import button
from undercover.bot.message_utils import show_or_resend_text
from undercover.game.engine import MAX_PLAYERS, CategoryRecord
from undercover.game.models import LobbyState, LobbyView
from undercover.redis.lobby_state import LobbyRepository
from undercover.texts import Buttons, Lobby
from undercover.texts import Setup as SetupTexts

JOIN_PAYLOAD_PREFIX: Final = "join_"

MIN_CATEGORIES_TO_CHOOSE: Final = 2
CATEGORIES_PER_ROW: Final = 2


class LobbyAction(StrEnum):
    JOIN = "join"
    LEAVE = "leave"
    SPIES = "spies"
    CATEGORIES = "cats"
    CATEGORY = "cat"
    DONE = "done"
    PLAY = "play"


class LobbyCB(CallbackData, prefix="lobby"):
    action: LobbyAction
    value: int = 0


async def render_lobby(
    bot: Bot,
    lobbies: LobbyRepository,
    lobby: LobbyState,
    categories: Sequence[CategoryRecord],
) -> None:
    lobby.message_id = await show_or_resend_text(
        bot,
        lobby.chat_id,
        lobby.message_id,
        lobby_text(lobby, categories),
        lobby_keyboard(lobby, categories),
    )
    await lobbies.save(lobby)


async def join_link(bot: Bot, chat_id: int) -> str:
    return await create_start_link(bot, f"{JOIN_PAYLOAD_PREFIX}{chat_id}", encode=False)


def lobby_text(lobby: LobbyState, categories: Sequence[CategoryRecord]) -> str:
    if lobby.view is LobbyView.CATEGORIES:
        return Lobby.PICK_CATEGORIES

    return "\n\n".join(
        (
            Lobby.TITLE,
            _roster(lobby),
            Lobby.SUMMARY.format(
                players_count=len(lobby.players),
                spies_count=lobby.spies_count,
                chosen_categories=_chosen_categories(lobby, categories),
            ),
            Lobby.CALL,
        )
    )


def lobby_keyboard(
    lobby: LobbyState, categories: Sequence[CategoryRecord]
) -> InlineKeyboardMarkup:
    if lobby.view is LobbyView.CATEGORIES:
        return _categories_keyboard(lobby, categories)
    return _roster_keyboard(lobby, categories)


def _roster(lobby: LobbyState) -> str:
    if not lobby.players:
        return Lobby.EMPTY_ROSTER
    return Lobby.ROSTER.format(
        count=len(lobby.players),
        limit=MAX_PLAYERS,
        names_list="\n".join(
            f"{number}. {player.name}" for number, player in enumerate(lobby.players, start=1)
        ),
    )


def _chosen_categories(lobby: LobbyState, categories: Sequence[CategoryRecord]) -> str:
    chosen = [item.title for item in categories if item.id in lobby.category_ids]
    return ", ".join(chosen) if chosen else SetupTexts.ALL_CATEGORIES


def _roster_keyboard(
    lobby: LobbyState, categories: Sequence[CategoryRecord]
) -> InlineKeyboardMarkup:
    settings = [_lobby_button(Buttons.SPIES_COUNT.format(count=lobby.spies_count), LobbyAction.SPIES)]
    if len(categories) >= MIN_CATEGORIES_TO_CHOOSE:
        settings.append(_lobby_button(Buttons.CHANGE_CATEGORIES, LobbyAction.CATEGORIES))

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _lobby_button(Buttons.JOIN_LOBBY, LobbyAction.JOIN),
                _lobby_button(Buttons.LEAVE_LOBBY, LobbyAction.LEAVE),
            ],
            settings,
            [_lobby_button(Buttons.PLAY, LobbyAction.PLAY)],
        ]
    )


def _categories_keyboard(
    lobby: LobbyState, categories: Sequence[CategoryRecord]
) -> InlineKeyboardMarkup:
    marks = [
        _lobby_button(
            (
                Lobby.CATEGORY_CHOSEN if item.id in lobby.category_ids else Lobby.CATEGORY_FREE
            ).format(title=item.title),
            LobbyAction.CATEGORY,
            item.id,
        )
        for item in categories
    ]
    rows = [
        marks[index : index + CATEGORIES_PER_ROW]
        for index in range(0, len(marks), CATEGORIES_PER_ROW)
    ]
    rows.append([_lobby_button(Buttons.CATEGORIES_DONE, LobbyAction.DONE)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _lobby_button(text: str, action: LobbyAction, value: int = 0) -> InlineKeyboardButton:
    return button(text, LobbyCB(action=action, value=value))
```

- [x] **Step 6: Прогнать проверки**

Run: `poetry run ruff check . && poetry run mypy && poetry run pytest -m "not integration" -q`
Expected: PASS. Если `tests/test_texts.py` проверяет полный перечень констант — дополнить его новыми.

---

## Task 11: Лобби открывается, игроки входят и выходят

**Files:**
- Create: `src/undercover/bot/routers/lobby.py`
- Create: `tests/lobby_harness.py`
- Modify: `tests/fake_bot.py`
- Test: `tests/test_lobby_router.py` (create)

**Interfaces:**
- Consumes: `LobbyCB`, `LobbyAction`, `render_lobby`, `join_link` (Task 10); `join`, `leave`, `unique_name` (Task 1); `FakeLobbyRepository` (Task 3)
- Produces: `create_lobby_router(open_catalog: CatalogFactory, start_discussion: PhaseStarter) -> Router` — в этой задаче обрабатываются `/game`, `JOIN`, `LEAVE`; `start_discussion` пока не используется, но входит в сигнатуру, потому что Task 13 без него не соберётся

- [x] **Step 1: Дополнить `tests/fake_bot.py`**

Добавить `chat_type` в `message_update`, чтобы можно было слать апдейт из личного чата:

```python
def message_update(
    text: str,
    *,
    user_id: int = HOST_ID,
    chat_id: int = CHAT_ID,
    chat_type: str = "group",
    update_id: int = 1,
) -> Update:
    return Update(
        update_id=update_id,
        message=Message(
            message_id=update_id,
            date=datetime.now(UTC),
            chat=Chat(id=chat_id, type=chat_type),
            from_user=User(id=user_id, is_bot=False, first_name="Ведущий"),
            text=text,
        ),
    )
```

`create_start_link` дергает `getMe`, поэтому в `_default_result` добавить (импортировав `GetMe` из `aiogram.methods` и `User` уже есть):

```python
        if isinstance(method, GetMe):
            return User(id=1, is_bot=True, first_name="Undercover", username="undercover_bot")
```

- [x] **Step 2: Создать `tests/lobby_harness.py`**

```python
from dataclasses import dataclass

from aiogram import Bot, Dispatcher
from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendMessage
from aiogram.types import InlineKeyboardMarkup

from fake_bot import CHAT_ID, HOST_ID, FakeSession, callback_update, make_bot, message_update
from fake_games import FakeGameStateRepository
from fake_lobbies import FakeLobbyRepository
from fake_words import FakeWords, catalog, pizza


@dataclass(frozen=True, slots=True)
class Screen:
    text: str
    buttons: tuple[tuple[str, str], ...]

    @property
    def texts(self) -> tuple[str, ...]:
        return tuple(text for text, _ in self.buttons)

    def callback_data(self, button_text: str) -> str:
        found = dict(self.buttons).get(button_text)
        assert found is not None, f"на экране нет кнопки «{button_text}»: {self.texts}"
        return found


@dataclass(frozen=True, slots=True)
class Group:
    dispatcher: Dispatcher
    bot: Bot
    session: FakeSession
    games: FakeGameStateRepository
    lobbies: FakeLobbyRepository
    words: FakeWords

    async def command(self, text: str, *, user_id: int = HOST_ID) -> None:
        await self.dispatcher.feed_update(
            self.bot, message_update(text, user_id=user_id, update_id=self._next_update)
        )

    async def press(self, button_text: str, *, user_id: int = HOST_ID) -> None:
        await self.tap(self.screen.callback_data(button_text), user_id=user_id)

    async def tap(self, data: str, *, user_id: int = HOST_ID) -> None:
        await self.dispatcher.feed_update(
            self.bot, callback_update(data, user_id=user_id, update_id=self._next_update)
        )

    @property
    def screen(self) -> Screen:
        screens = self.screens
        assert screens, "лобби ещё не нарисовано"
        return screens[-1]

    @property
    def screens(self) -> list[Screen]:
        result: list[Screen] = []
        for request in self.session.requests:
            if isinstance(request, SendMessage | EditMessageText):
                markup = request.reply_markup
                result.append(
                    Screen(
                        text=request.text,
                        buttons=tuple(
                            (item.text, item.callback_data)
                            for row in (
                                markup.inline_keyboard
                                if isinstance(markup, InlineKeyboardMarkup)
                                else []
                            )
                            for item in row
                            if item.callback_data is not None
                        ),
                    )
                )
        return result

    @property
    def alerts(self) -> list[str | None]:
        return [answer.text for answer in self.session.calls(AnswerCallbackQuery)]

    @property
    def redirects(self) -> list[str | None]:
        return [answer.url for answer in self.session.calls(AnswerCallbackQuery)]

    @property
    def _next_update(self) -> int:
        return len(self.session.requests) + 1
```

Фикстуру `group` объявить в `tests/test_lobby_router.py` — она собирает диспетчер из `create_lobby_router(words.open, start_discussion)`.

- [x] **Step 3: Написать падающие тесты**

Создать `tests/test_lobby_router.py`:

```python
from typing import Final

import pytest
from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramForbiddenError
from aiogram.methods import SendMessage

from fake_bot import CHAT_ID, HOST_ID, FakeSession, make_bot
from fake_games import FakeGameStateRepository
from fake_lobbies import FakeLobbyRepository
from fake_words import FakeWords, catalog, pizza
from lobby_harness import Group
from undercover.bot.routers.discussion import start_discussion
from undercover.bot.routers.lobby import create_lobby_router
from undercover.game.models import LobbyPlayer, LobbyState
from undercover.texts import Buttons, Errors, Lobby

GUEST_ID: Final = 555
OTHER_ID: Final = 666


@pytest.fixture
def words() -> FakeWords:
    return FakeWords(pizza(), categories=catalog("Еда", "Города"))


@pytest.fixture
def group(words: FakeWords) -> Group:
    session = FakeSession()
    games = FakeGameStateRepository()
    lobbies = FakeLobbyRepository()
    dispatcher = Dispatcher(games=games, lobbies=lobbies)
    dispatcher.include_router(create_lobby_router(words.open, start_discussion))
    return Group(
        dispatcher=dispatcher,
        bot=make_bot(session),
        session=session,
        games=games,
        lobbies=lobbies,
        words=words,
    )


async def test_game_opens_a_lobby_with_the_sender_as_host(group: Group) -> None:
    await group.command("/game")

    assert group.lobbies.stored.host_user_id == HOST_ID
    assert group.screen.texts[0] == Buttons.JOIN_LOBBY


async def test_game_refuses_while_a_game_is_running_in_the_chat(
    group: Group, running_game: None
) -> None:
    await group.command("/game")

    assert group.lobbies.is_empty
    assert Errors.GAME_IN_CHAT in [call.text for call in group.session.calls(SendMessage)]


async def test_game_reopens_an_existing_lobby_without_losing_the_roster(group: Group) -> None:
    await group.command("/game")
    await group.press(Buttons.JOIN_LOBBY, user_id=GUEST_ID)

    await group.command("/game")

    assert [player.user_id for player in group.lobbies.stored.players] == [GUEST_ID]


async def test_joining_pings_the_private_chat_and_shows_the_name_in_the_roster(
    group: Group,
) -> None:
    await group.command("/game")

    await group.press(Buttons.JOIN_LOBBY, user_id=GUEST_ID)

    assert Lobby.DM_WELCOME in [call.text for call in group.session.calls(SendMessage)]
    assert len(group.lobbies.stored.players) == 1


async def test_a_closed_private_chat_redirects_to_the_deep_link_instead_of_joining(
    group: Group,
) -> None:
    await group.command("/game")
    group.session.failures[SendMessage] = TelegramForbiddenError(
        method=SendMessage(chat_id=GUEST_ID, text="x"), message="bot can't initiate conversation"
    )

    await group.press(Buttons.JOIN_LOBBY, user_id=GUEST_ID)

    assert group.lobbies.stored.players == []
    assert any(url and f"start=join_{CHAT_ID}" in url for url in group.redirects)


async def test_joining_twice_is_refused_without_a_second_ping(group: Group) -> None:
    await group.command("/game")
    await group.press(Buttons.JOIN_LOBBY, user_id=GUEST_ID)
    pings = len(group.session.calls(SendMessage))

    await group.press(Buttons.JOIN_LOBBY, user_id=GUEST_ID)

    assert Lobby.ALREADY_IN in group.alerts
    assert len(group.session.calls(SendMessage)) == pings


async def test_two_players_with_the_same_telegram_name_get_told_apart(group: Group) -> None:
    await group.command("/game")

    await group.press(Buttons.JOIN_LOBBY, user_id=GUEST_ID)
    await group.press(Buttons.JOIN_LOBBY, user_id=OTHER_ID)

    names = [player.name for player in group.lobbies.stored.players]
    assert len(set(names)) == 2


async def test_leaving_removes_the_player(group: Group) -> None:
    await group.command("/game")
    await group.press(Buttons.JOIN_LOBBY, user_id=GUEST_ID)

    await group.press(Buttons.LEAVE_LOBBY, user_id=GUEST_ID)

    assert group.lobbies.stored.players == []


async def test_leaving_when_never_joined_says_so(group: Group) -> None:
    await group.command("/game")

    await group.press(Buttons.LEAVE_LOBBY, user_id=GUEST_ID)

    assert Lobby.NOT_IN in group.alerts


async def test_a_button_from_a_closed_lobby_says_it_is_closed(group: Group) -> None:
    await group.command("/game")
    data = group.screen.callback_data(Buttons.JOIN_LOBBY)
    await group.lobbies.delete(CHAT_ID)

    await group.tap(data, user_id=GUEST_ID)

    assert Errors.LOBBY_CLOSED in group.alerts


async def test_game_in_a_private_chat_points_to_a_group(group: Group) -> None:
    await group.dispatcher.feed_update(
        group.bot, message_update("/game", chat_id=HOST_ID, chat_type="private")
    )

    assert Errors.GROUP_ONLY in [call.text for call in group.session.calls(SendMessage)]
```

Фикстура `running_game` кладёт в `group.games` активную сессию этого чата — собрать её через `GameSessionState` так же, как в `tests/test_discussion.py`. `message_update` импортировать из `fake_bot`. У обоих игроков `fake_bot.callback_update` ставит `first_name="Ведущий"`, что и делает имена одинаковыми, — ровно то, что проверяет тест на `unique_name`.

- [x] **Step 4: Убедиться, что тесты падают**

Run: `poetry run pytest tests/test_lobby_router.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'undercover.bot.routers.lobby'`

- [x] **Step 5: Создать `bot/routers/lobby.py`**

```python
import logging
from collections.abc import Sequence
from typing import Final

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramForbiddenError
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from undercover.bot.lobby_view import LobbyAction, LobbyCB, join_link, render_lobby
from undercover.bot.routers.reveal import PhaseStarter
from undercover.game.engine import CatalogFactory, CategoryRecord, GameRulesError
from undercover.game.lobby import join, leave, unique_name
from undercover.game.models import LobbyPlayer, LobbyState
from undercover.redis.game_state import GameStateRepository
from undercover.redis.lobby_state import LobbyRepository
from undercover.texts import Errors, Lobby

logger = logging.getLogger(__name__)

GROUP_CHATS: Final = frozenset({"group", "supergroup"})


def create_lobby_router(open_catalog: CatalogFactory, start_discussion: PhaseStarter) -> Router:
    router = Router(name="lobby")

    async def redraw(bot: Bot, lobbies: LobbyRepository, lobby: LobbyState) -> None:
        await render_lobby(bot, lobbies, lobby, await _categories(open_catalog))

    @router.message(Command("game"), F.chat.type.in_(GROUP_CHATS))
    async def cmd_game(
        message: Message, bot: Bot, games: GameStateRepository, lobbies: LobbyRepository
    ) -> None:
        if message.from_user is None:
            return
        if await games.load_active(message.chat.id) is not None:
            await message.answer(Errors.GAME_IN_CHAT)
            return

        lobby = await lobbies.load(message.chat.id) or LobbyState(
            chat_id=message.chat.id, host_user_id=message.from_user.id
        )
        lobby.message_id = None
        await redraw(bot, lobbies, lobby)

    @router.message(Command("game"))
    async def cmd_game_elsewhere(message: Message) -> None:
        await message.answer(Errors.GROUP_ONLY)

    @router.callback_query(LobbyCB.filter(F.action == LobbyAction.JOIN))
    async def cb_join(callback: CallbackQuery, bot: Bot, lobbies: LobbyRepository) -> None:
        lobby = await _open_lobby(callback, lobbies)
        if lobby is None:
            return
        if lobby.index_of(callback.from_user.id) is not None:
            await callback.answer(Lobby.ALREADY_IN, show_alert=True)
            return
        if not await _ping_direct_chat(bot, callback, lobby.chat_id):
            return

        player = LobbyPlayer(
            user_id=callback.from_user.id,
            name=unique_name(
                callback.from_user.full_name, [member.name for member in lobby.players]
            ),
        )
        try:
            join(lobby, player)
        except GameRulesError as error:
            await callback.answer(str(error), show_alert=True)
            return

        await redraw(bot, lobbies, lobby)
        await callback.answer()

    @router.callback_query(LobbyCB.filter(F.action == LobbyAction.LEAVE))
    async def cb_leave(callback: CallbackQuery, bot: Bot, lobbies: LobbyRepository) -> None:
        lobby = await _open_lobby(callback, lobbies)
        if lobby is None:
            return
        try:
            leave(lobby, callback.from_user.id)
        except GameRulesError:
            await callback.answer(Lobby.NOT_IN, show_alert=True)
            return

        await redraw(bot, lobbies, lobby)
        await callback.answer()

    return router


async def _categories(open_catalog: CatalogFactory) -> Sequence[CategoryRecord]:
    async with open_catalog() as catalog:
        return await catalog.list_playable_categories()


async def _open_lobby(
    callback: CallbackQuery, lobbies: LobbyRepository
) -> LobbyState | None:
    lobby = None if callback.message is None else await lobbies.load(callback.message.chat.id)
    if lobby is None:
        await callback.answer(Errors.LOBBY_CLOSED, show_alert=True)
    return lobby


async def _ping_direct_chat(bot: Bot, callback: CallbackQuery, chat_id: int) -> bool:
    try:
        await bot.send_message(callback.from_user.id, Lobby.DM_WELCOME)
    except TelegramForbiddenError:
        await callback.answer(url=await join_link(bot, chat_id))
        return False
    return True
```

- [x] **Step 6: Прогнать проверки**

Run: `poetry run ruff check . && poetry run mypy && poetry run pytest -m "not integration" -q`
Expected: PASS

---

## Task 12: Настройки прямо в лобби

**Files:**
- Modify: `src/undercover/bot/routers/lobby.py`
- Test: `tests/test_lobby_router.py` (modify)

**Interfaces:**
- Consumes: `cycle_spies_count`, `toggle_category` (Task 1); `LobbyView` (Task 1)
- Produces: обработчики `SPIES`, `CATEGORIES`, `CATEGORY`, `DONE` в том же роутере

- [x] **Step 1: Написать падающие тесты**

Добавить в `tests/test_lobby_router.py`:

```python
async def test_the_spies_button_walks_the_allowed_range_and_wraps(group: Group) -> None:
    await group.command("/game")
    for user_id in range(100, 106):
        await group.press(Buttons.JOIN_LOBBY, user_id=user_id)

    await group.press(Buttons.SPIES_COUNT.format(count=1))
    assert group.lobbies.stored.spies_count == 2

    await group.press(Buttons.SPIES_COUNT.format(count=2))
    assert group.lobbies.stored.spies_count == 1


async def test_only_the_host_changes_the_settings(group: Group) -> None:
    await group.command("/game")

    await group.press(Buttons.SPIES_COUNT.format(count=1), user_id=GUEST_ID)

    assert group.lobbies.stored.spies_count == 1
    assert Errors.NOT_HOST in group.alerts


async def test_categories_open_toggle_and_close(group: Group) -> None:
    await group.command("/game")

    await group.press(Buttons.CHANGE_CATEGORIES)
    assert group.lobbies.stored.view is LobbyView.CATEGORIES

    await group.press(Lobby.CATEGORY_FREE.format(title="Еда"))
    assert group.lobbies.stored.category_ids == [1]

    await group.press(Lobby.CATEGORY_CHOSEN.format(title="Еда"))
    assert group.lobbies.stored.category_ids == []

    await group.press(Buttons.CATEGORIES_DONE)
    assert group.lobbies.stored.view is LobbyView.ROSTER


async def test_a_category_button_from_a_stranger_changes_nothing(group: Group) -> None:
    await group.command("/game")
    await group.press(Buttons.CHANGE_CATEGORIES)
    data = group.screen.callback_data(Lobby.CATEGORY_FREE.format(title="Еда"))

    await group.tap(data, user_id=GUEST_ID)

    assert group.lobbies.stored.category_ids == []
    assert Errors.NOT_HOST in group.alerts
```

Случай «в словаре одна категория — кнопки настройки нет» уже закрыт на уровне
клавиатуры в `tests/test_lobby_view.py`; дублировать его через роутер незачем.

- [x] **Step 2: Убедиться, что тесты падают**

Run: `poetry run pytest tests/test_lobby_router.py -q -k "spies or categor"`
Expected: FAIL — кнопки не обрабатываются, состояние не меняется

- [x] **Step 3: Дописать обработчики в `create_lobby_router`**

```python
    @router.callback_query(LobbyCB.filter(F.action == LobbyAction.SPIES))
    async def cb_spies(callback: CallbackQuery, bot: Bot, lobbies: LobbyRepository) -> None:
        lobby = await _host_lobby(callback, lobbies)
        if lobby is None:
            return
        cycle_spies_count(lobby)
        await redraw(bot, lobbies, lobby)
        await callback.answer()

    @router.callback_query(LobbyCB.filter(F.action == LobbyAction.CATEGORIES))
    async def cb_categories(callback: CallbackQuery, bot: Bot, lobbies: LobbyRepository) -> None:
        lobby = await _host_lobby(callback, lobbies)
        if lobby is None:
            return
        lobby.view = LobbyView.CATEGORIES
        await redraw(bot, lobbies, lobby)
        await callback.answer()

    @router.callback_query(LobbyCB.filter(F.action == LobbyAction.CATEGORY))
    async def cb_category(
        callback: CallbackQuery,
        callback_data: LobbyCB,
        bot: Bot,
        lobbies: LobbyRepository,
    ) -> None:
        lobby = await _host_lobby(callback, lobbies)
        if lobby is None:
            return
        toggle_category(lobby, callback_data.value)
        await redraw(bot, lobbies, lobby)
        await callback.answer()

    @router.callback_query(LobbyCB.filter(F.action == LobbyAction.DONE))
    async def cb_categories_done(
        callback: CallbackQuery, bot: Bot, lobbies: LobbyRepository
    ) -> None:
        lobby = await _host_lobby(callback, lobbies)
        if lobby is None:
            return
        lobby.view = LobbyView.ROSTER
        await redraw(bot, lobbies, lobby)
        await callback.answer()
```

И общий помощник рядом с `_open_lobby`:

```python
async def _host_lobby(
    callback: CallbackQuery, lobbies: LobbyRepository
) -> LobbyState | None:
    lobby = await _open_lobby(callback, lobbies)
    if lobby is None:
        return None
    if callback.from_user.id != lobby.host_user_id:
        await callback.answer(Errors.NOT_HOST, show_alert=True)
        return None
    return lobby
```

Импорты дополнить: `cycle_spies_count`, `toggle_category` из `undercover.game.lobby`, `LobbyView` из `undercover.game.models`.

- [x] **Step 4: Прогнать проверки**

Run: `poetry run ruff check . && poetry run mypy && poetry run pytest -m "not integration" -q`
Expected: PASS

---

## Task 13: Старт групповой партии

**Files:**
- Modify: `src/undercover/bot/routers/lobby.py`
- Test: `tests/test_lobby_router.py` (modify)

**Interfaces:**
- Consumes: `ensure_playable` (Task 1), `create_session` с `player_ids`/`mode` (Task 2), `deliver_roles` (Task 5), `start_discussion` (Task 9), `join_link` (Task 10)
- Produces: обработчик `PLAY`

- [x] **Step 1: Написать падающие тесты**

```python
async def test_a_started_game_hands_out_roles_and_opens_the_first_turn(group: Group) -> None:
    await group.command("/game")
    await group.press(Buttons.JOIN_LOBBY, user_id=GUEST_ID)
    await group.press(Buttons.JOIN_LOBBY, user_id=OTHER_ID)

    await group.press(Buttons.PLAY)

    state = group.games.stored
    assert state.mode is GameMode.GROUP
    assert sorted(player.user_id for player in state.players) == sorted([GUEST_ID, OTHER_ID])
    assert [call.chat_id for call in group.session.calls(SendPhoto)][:2] == [GUEST_ID, OTHER_ID]
    assert group.lobbies.is_empty
    assert Lobby.STARTED in [screen.text for screen in group.screens]


async def test_the_lobby_settings_reach_the_session(group: Group) -> None:
    await group.command("/game")
    for user_id in range(100, 106):
        await group.press(Buttons.JOIN_LOBBY, user_id=user_id)
    await group.press(Buttons.SPIES_COUNT.format(count=1))
    await group.press(Buttons.CHANGE_CATEGORIES)
    await group.press(Lobby.CATEGORY_FREE.format(title="Еда"))
    await group.press(Buttons.CATEGORIES_DONE)

    await group.press(Buttons.PLAY)

    state = group.games.stored
    assert sum(player.is_spy for player in state.players) == 2
    assert state.category_ids == [1]


async def test_a_table_of_one_cannot_start(group: Group) -> None:
    await group.command("/game")
    await group.press(Buttons.JOIN_LOBBY, user_id=GUEST_ID)

    await group.press(Buttons.PLAY)

    assert group.games.is_empty
    assert group.lobbies.stored.players != []


async def test_only_the_host_starts_the_game(group: Group) -> None:
    await group.command("/game")
    await group.press(Buttons.JOIN_LOBBY, user_id=GUEST_ID)
    await group.press(Buttons.JOIN_LOBBY, user_id=OTHER_ID)

    await group.press(Buttons.PLAY, user_id=GUEST_ID)

    assert group.games.is_empty
    assert Errors.NOT_HOST in group.alerts


async def test_an_undelivered_role_cancels_the_start_and_keeps_the_lobby(group: Group) -> None:
    await group.command("/game")
    await group.press(Buttons.JOIN_LOBBY, user_id=GUEST_ID)
    await group.press(Buttons.JOIN_LOBBY, user_id=OTHER_ID)
    group.session.failures[SendPhoto] = TelegramForbiddenError(
        method=SendPhoto(chat_id=GUEST_ID, photo="x"), message="bot was blocked by the user"
    )

    await group.press(Buttons.PLAY)

    assert group.games.is_empty
    assert len(group.lobbies.stored.players) == 2
    assert Lobby.DELIVERY_FAILED in group.alerts
    assert any("start=join_" in (screen.text or "") for screen in group.screens)


async def test_an_empty_dictionary_stops_the_start_without_losing_the_roster(
    group: Group,
) -> None:
    await group.command("/game")
    await group.press(Buttons.JOIN_LOBBY, user_id=GUEST_ID)
    await group.press(Buttons.JOIN_LOBBY, user_id=OTHER_ID)
    group.words.word = None

    await group.press(Buttons.PLAY)

    assert group.games.is_empty
    assert len(group.lobbies.stored.players) == 2
```

`FakeGameStateRepository` дополнить свойством `is_empty`, зеркалящим `FakeLobbyRepository.is_empty`.

- [x] **Step 2: Убедиться, что тесты падают**

Run: `poetry run pytest tests/test_lobby_router.py -q -k "start or host or dictionary or undelivered"`
Expected: FAIL — кнопка «Начать партию» ничего не делает

- [x] **Step 3: Дописать обработчик `PLAY`**

```python
    @router.callback_query(LobbyCB.filter(F.action == LobbyAction.PLAY))
    async def cb_play(
        callback: CallbackQuery,
        bot: Bot,
        games: GameStateRepository,
        lobbies: LobbyRepository,
    ) -> None:
        lobby = await _host_lobby(callback, lobbies)
        if lobby is None:
            return
        if await games.load_active(lobby.chat_id) is not None:
            await callback.answer(Errors.GAME_IN_CHAT, show_alert=True)
            return
        try:
            ensure_playable(lobby)
        except GameRulesError as error:
            await callback.answer(str(error), show_alert=True)
            return

        try:
            async with open_catalog() as words:
                state = await create_session(
                    chat_id=lobby.chat_id,
                    host_user_id=lobby.host_user_id,
                    player_names=[player.name for player in lobby.players],
                    player_ids=[player.user_id for player in lobby.players],
                    spies_count=lobby.spies_count,
                    words=words,
                    rng=secure_rng(),
                    category_ids=lobby.category_ids,
                    mode=GameMode.GROUP,
                )
        except EmptyWordCatalogError:
            logger.exception("чат %s: партию не собрать, словарь пуст", lobby.chat_id)
            await callback.answer(empty_catalog_text(lobby.category_ids), show_alert=True)
            return

        undelivered = await deliver_roles(bot, state)
        if undelivered:
            await callback.answer(Lobby.DELIVERY_FAILED, show_alert=True)
            await bot.send_message(
                lobby.chat_id,
                Lobby.OPEN_DM.format(
                    names=", ".join(player.name for player in undelivered)
                )
                + f"\n{await join_link(bot, lobby.chat_id)}",
            )
            return

        await games.save(state)
        await lobbies.delete(lobby.chat_id)
        await show_or_resend_text(bot, lobby.chat_id, lobby.message_id, Lobby.STARTED)
        await start_discussion(bot, games, state)
        await callback.answer()
```

Импорты дополнить: `ensure_playable` из `undercover.game.lobby`; `EmptyWordCatalogError`, `create_session` из `undercover.game.engine`; `GameMode` из `undercover.game.models`; `deliver_roles` из `undercover.bot.role_delivery`; `show_or_resend_text` из `undercover.bot.message_utils`; `secure_rng` из `undercover.utils.secure_random`; `empty_catalog_text` из `undercover.texts`.

Порядок здесь и есть защита: сессия сохраняется и лобби удаляется только после того, как карточки дошли всем.

- [x] **Step 4: Прогнать проверки**

Run: `poetry run ruff check . && poetry run mypy && poetry run pytest -m "not integration" -q`
Expected: PASS

---

## Task 14: Вход в лобби по deep-link

**Files:**
- Modify: `src/undercover/bot/routers/start.py`
- Test: `tests/test_start.py` (modify)

**Interfaces:**
- Consumes: `JOIN_PAYLOAD_PREFIX`, `render_lobby` (Task 10); `join`, `unique_name` (Task 1)
- Produces: `create_start_router(open_catalog: CatalogFactory) -> Router` — прежний `cmd_start` плюс обработчик `/start join_<chat_id>`

- [x] **Step 1: Написать падающие тесты**

Добавить в `tests/test_start.py`:

```python
GUEST_ID: Final = 555


@dataclass(frozen=True, slots=True)
class Private:
    dispatcher: Dispatcher
    bot: Bot
    session: FakeSession
    lobbies: FakeLobbyRepository

    async def start(self, payload: str = "", *, user_id: int = GUEST_ID) -> None:
        text = f"/start {payload}".strip()
        await self.dispatcher.feed_update(
            self.bot, message_update(text, user_id=user_id, chat_id=user_id, chat_type="private")
        )

    @property
    def replies(self) -> list[str]:
        return [call.text for call in self.session.calls(SendMessage)]


@pytest.fixture
def private(words: FakeWords) -> Private:
    session = FakeSession()
    lobbies = FakeLobbyRepository(LobbyState(chat_id=CHAT_ID, host_user_id=HOST_ID))
    dispatcher = Dispatcher(storage=JsonMemoryStorage(), lobbies=lobbies)
    dispatcher.include_router(create_start_router(words.open))
    dispatcher.include_router(create_setup_dialog(words.open, start_reveal))
    setup_dialogs(dispatcher, message_manager=MockMessageManager())
    return Private(
        dispatcher=dispatcher, bot=make_bot(session), session=session, lobbies=lobbies
    )


async def test_a_deep_link_start_puts_the_player_into_the_lobby_of_that_chat(
    private: Private,
) -> None:
    await private.start(f"join_{CHAT_ID}")

    assert [player.user_id for player in private.lobbies.stored.players] == [GUEST_ID]
    assert Lobby.DM_WELCOME in private.replies


async def test_a_deep_link_redraws_the_lobby_in_the_group(private: Private) -> None:
    await private.start(f"join_{CHAT_ID}")

    assert any(call.chat_id == CHAT_ID for call in private.session.calls(SendMessage))


async def test_a_deep_link_to_a_closed_lobby_says_so(private: Private) -> None:
    await private.lobbies.delete(CHAT_ID)

    await private.start(f"join_{CHAT_ID}")

    assert Errors.LOBBY_CLOSED in private.replies


async def test_a_deep_link_from_someone_already_in_the_lobby_does_not_duplicate(
    private: Private,
) -> None:
    await private.start(f"join_{CHAT_ID}")

    await private.start(f"join_{CHAT_ID}")

    assert len(private.lobbies.stored.players) == 1
    assert Lobby.ALREADY_IN in private.replies


async def test_a_deep_link_with_junk_does_not_reach_the_lobby_handler(
    private: Private,
) -> None:
    await private.start("join_не-число")

    assert private.lobbies.stored.players == []
    assert Start.GREETING in private.replies


async def test_a_plain_start_still_opens_the_hot_seat_setup(private: Private) -> None:
    await private.start()

    assert Start.GREETING in private.replies
    assert private.lobbies.stored.players == []
```

Мусорный payload проверяется отдельно: `F.args.regexp` не пропускает его в обработчик
лобби, и апдейт достаётся обычному `cmd_start` — то есть регистрация в правильном
порядке действительно работает.

- [x] **Step 2: Убедиться, что тесты падают**

Run: `poetry run pytest tests/test_start.py -q`
Expected: FAIL — deep-link не разбирается, игрок в лобби не попадает

- [x] **Step 3: Переписать `bot/routers/start.py`**

```python
import re
from typing import Final

from aiogram import Bot, F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import Message
from aiogram_dialog import DialogManager, StartMode

from undercover.bot.lobby_view import JOIN_PAYLOAD_PREFIX, render_lobby
from undercover.bot.routers.setup_dialog import Setup
from undercover.game.engine import CatalogFactory, GameRulesError
from undercover.game.lobby import join, unique_name
from undercover.game.models import LobbyPlayer
from undercover.redis.lobby_state import LobbyRepository
from undercover.texts import Errors, Lobby, Start

JOIN_PAYLOAD: Final = re.compile(rf"^{JOIN_PAYLOAD_PREFIX}(-?\d+)$")


def create_start_router(open_catalog: CatalogFactory) -> Router:
    router = Router(name="start")

    @router.message(CommandStart(deep_link=True, magic=F.args.regexp(JOIN_PAYLOAD)))
    async def cmd_join_lobby(
        message: Message,
        command: CommandObject,
        bot: Bot,
        lobbies: LobbyRepository,
    ) -> None:
        payload = JOIN_PAYLOAD.match(command.args or "")
        if payload is None or message.from_user is None:
            return

        lobby = await lobbies.load(int(payload.group(1)))
        if lobby is None:
            await message.answer(Errors.LOBBY_CLOSED)
            return
        if lobby.index_of(message.from_user.id) is not None:
            await message.answer(Lobby.ALREADY_IN)
            return

        player = LobbyPlayer(
            user_id=message.from_user.id,
            name=unique_name(
                message.from_user.full_name, [member.name for member in lobby.players]
            ),
        )
        try:
            join(lobby, player)
        except GameRulesError as error:
            await message.answer(str(error))
            return

        await message.answer(Lobby.DM_WELCOME)
        async with open_catalog() as catalog:
            categories = await catalog.list_playable_categories()
        await render_lobby(bot, lobbies, lobby, categories)

    @router.message(CommandStart())
    async def cmd_start(message: Message, dialog_manager: DialogManager) -> None:
        await message.answer(Start.GREETING)
        await dialog_manager.start(Setup.ask_players_count, mode=StartMode.RESET_STACK)

    return router
```

Порядок регистрации важен: обработчик deep-link объявлен первым, иначе `CommandStart()` перехватит и его.

- [x] **Step 4: Прогнать проверки**

Run: `poetry run ruff check . && poetry run mypy && poetry run pytest -m "not integration" -q`
Expected: PASS

---

## Task 15: Проводка и меню команд

**Files:**
- Modify: `src/undercover/bot/dispatcher.py`
- Test: `tests/test_dispatcher.py` (modify)

**Interfaces:**
- Consumes: всё из Task 8, 11–14
- Produces: `create_dispatcher` включает `create_lobby_router`; `_publish_commands` публикует `/start` везде и `/start` + `/game` в группах

- [x] **Step 1: Написать падающие тесты**

Добавить в `tests/test_dispatcher.py`:

```python
async def test_group_chats_see_the_game_command_in_the_menu() -> None:
    session = FakeSession()
    bot = make_bot(session)

    await _publish_commands(bot)

    scopes = session.calls(SetMyCommands)
    assert any(
        isinstance(call.scope, BotCommandScopeAllGroupChats)
        and [command.command for command in call.commands] == ["start", "game"]
        for call in scopes
    )


async def test_private_chats_are_not_offered_a_group_only_command() -> None:
    session = FakeSession()

    await _publish_commands(make_bot(session))

    default_calls = [call for call in session.calls(SetMyCommands) if call.scope is None]
    assert all(
        "game" not in [command.command for command in call.commands] for call in default_calls
    )


def test_the_lobby_router_is_wired_in(dependencies: AppDependencies) -> None:
    dispatcher = create_dispatcher(dependencies)

    assert "lobby" in [router.name for router in dispatcher.sub_routers]
```

Существующий тест на `resolve_allowed_updates` должен остаться зелёным.

- [x] **Step 2: Убедиться, что тесты падают**

Run: `poetry run pytest tests/test_dispatcher.py -q`
Expected: FAIL — роутер лобби не подключён, меню публикуется одним набором

- [x] **Step 3: Переписать проводку**

```python
def create_dispatcher(dependencies: AppDependencies) -> Dispatcher:
    dispatcher = Dispatcher(
        storage=_create_storage(dependencies),
        **dependencies.as_workflow_data(),
    )

    throttling = ThrottlingMiddleware()
    dispatcher.message.outer_middleware(throttling)
    dispatcher.callback_query.outer_middleware(throttling)

    open_words = words_source(dependencies.sessionmaker)
    log_game = game_log_writer(dependencies.sessionmaker)

    dispatcher.include_router(create_start_router(open_words))
    dispatcher.include_router(create_lobby_router(open_words, start_discussion))
    dispatcher.include_router(create_setup_dialog(open_words, start_reveal))
    dispatcher.include_router(create_reveal_router(start_discussion))
    dispatcher.include_router(create_discussion_router())
    dispatcher.include_router(create_finale_router(open_words, log_game))
    dispatcher.include_router(create_error_router())

    setup_dialogs(dispatcher)
    dispatcher.startup.register(_publish_commands)
    return dispatcher
```

`words_source(...)` уже отдаёт полный каталог (`WordsRepository` реализует и `list_playable_categories`), поэтому он же служит `CatalogFactory`.

```python
async def _publish_commands(bot: Bot) -> None:
    start = BotCommand(command="start", description=Start.COMMAND_DESCRIPTION)
    game = BotCommand(command="game", description=Start.GAME_COMMAND_DESCRIPTION)
    try:
        await bot.set_my_commands([start])
        await bot.set_my_commands([start, game], scope=BotCommandScopeAllGroupChats())
    except Exception as error:
        logger.warning("не удалось опубликовать меню команд: %s", error)
```

- [x] **Step 4: Прогнать проверки**

Run: `poetry run ruff check . && poetry run ruff format --check . && poetry run mypy && poetry run pytest -q`
Expected: PASS. Прогнать и интеграционные тесты — это последняя задача фазы, где меняется сборка приложения.

---

## Task 16: README о групповом режиме

**Files:**
- Modify: `README.md`

- [x] **Step 1: Переписать вводный абзац**

Сейчас там «игра в шпиона на одном телефоне». Режимов стало два — сказать про оба: hot-seat с передачей телефона и групповой, где `/game` открывает лобби, а роли уходят каждому в личку.

- [x] **Step 2: Дописать раздел «Как играть»**

Изложить: `/game` в группе поднимает лобби; «Я в игре» пишет игроку в личку, а если бот у него не открыт — Telegram сам перекинет по ссылке; ведущий выставляет шпионов и категории кнопками там же; «Начать партию» раздаёт карточки и открывает первый ход; каждый ход приходит новым сообщением, предыдущее замирает отчётом; «Дальше» нажимает ведущий или тот, чей ход.

- [x] **Step 3: Поправить оговорку про privacy mode**

Групповому режиму privacy mode не мешает — команды со слешем Telegram доставляет боту всегда. Выключать его нужно только для hot-seat в группе, где имена вводятся обычными сообщениями. Сейчас README требует выключать безусловно.

- [x] **Step 4: Проверить**

Run: `poetry run pytest -m "not integration" -q`
Expected: PASS. Прочитать README глазами: бренд везде `Undercover`, эмодзи нет.

---

# Фаза 2. Таймер хода

## Task 17: Блокировки по ключу

Без них таймер и кнопка успевают оба прочитать `cursor=2`, оба увидеть совпадение и оба продвинуть ход до 3 — в чат уйдут два сообщения об одном говорящем. Сверка `(round, cursor)` эту гонку не ловит: она происходит между `load` и `save`.

**Files:**
- Create: `src/undercover/utils/keyed_locks.py`
- Test: `tests/test_keyed_locks.py` (create)

**Interfaces:**
- Produces: `KeyedLocks()` с асинхронным контекст-менеджером `held(key: str)` и свойством `busy_keys: frozenset[str]`

- [ ] **Step 1: Написать падающие тесты**

Создать `tests/test_keyed_locks.py`:

```python
import asyncio

import pytest

from undercover.utils.keyed_locks import KeyedLocks


async def test_the_same_key_runs_one_at_a_time() -> None:
    locks = KeyedLocks()
    trace: list[str] = []

    async def worker(name: str) -> None:
        async with locks.held("game"):
            trace.append(f"{name}-in")
            await asyncio.sleep(0)
            trace.append(f"{name}-out")

    await asyncio.gather(worker("a"), worker("b"))

    assert trace in (
        ["a-in", "a-out", "b-in", "b-out"],
        ["b-in", "b-out", "a-in", "a-out"],
    )


async def test_different_keys_do_not_wait_for_each_other() -> None:
    locks = KeyedLocks()
    entered = asyncio.Event()

    async def holder() -> None:
        async with locks.held("first"):
            entered.set()
            await asyncio.sleep(0.05)

    async def passer() -> None:
        await entered.wait()
        async with locks.held("second"):
            return

    await asyncio.wait_for(asyncio.gather(holder(), passer()), timeout=1)


async def test_a_finished_key_is_forgotten_so_the_registry_does_not_grow() -> None:
    locks = KeyedLocks()

    async with locks.held("game"):
        assert locks.busy_keys == frozenset({"game"})

    assert locks.busy_keys == frozenset()


async def test_a_raising_block_still_releases_the_key() -> None:
    locks = KeyedLocks()

    with pytest.raises(RuntimeError):
        async with locks.held("game"):
            raise RuntimeError("боом")

    assert locks.busy_keys == frozenset()
    async with locks.held("game"):
        pass


async def test_a_nested_wait_keeps_the_same_lock_object_alive() -> None:
    locks = KeyedLocks()
    order: list[int] = []

    async def worker(number: int) -> None:
        async with locks.held("game"):
            order.append(number)
            await asyncio.sleep(0)

    await asyncio.gather(*(worker(number) for number in range(5)))

    assert sorted(order) == list(range(5))
    assert locks.busy_keys == frozenset()
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `poetry run pytest tests/test_keyed_locks.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'undercover.utils.keyed_locks'`

- [ ] **Step 3: Реализовать**

```python
from asyncio import Lock
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager


class KeyedLocks:
    def __init__(self) -> None:
        self._locks: dict[str, tuple[Lock, int]] = {}

    @asynccontextmanager
    async def held(self, key: str) -> AsyncIterator[None]:
        lock = self._reserve(key)
        try:
            async with lock:
                yield
        finally:
            self._release(key)

    @property
    def busy_keys(self) -> frozenset[str]:
        return frozenset(self._locks)

    def _reserve(self, key: str) -> Lock:
        lock, waiters = self._locks.get(key, (Lock(), 0))
        self._locks[key] = (lock, waiters + 1)
        return lock

    def _release(self, key: str) -> None:
        lock, waiters = self._locks[key]
        if waiters <= 1:
            del self._locks[key]
        else:
            self._locks[key] = (lock, waiters - 1)
```

Счётчик ожидающих обязателен: без него ключ удалялся бы первым же вышедшим, второй желающий получил бы **новый** `Lock` и прошёл насквозь.

- [ ] **Step 4: Прогнать проверки**

Run: `poetry run ruff check . && poetry run mypy && poetry run pytest -m "not integration" -q`
Expected: PASS

---

## Task 18: Длительность хода в модели и в лобби

**Files:**
- Modify: `src/undercover/game/models.py`
- Modify: `src/undercover/game/lobby.py`
- Modify: `src/undercover/game/engine.py` (`create_session` получает `turn_seconds`)
- Modify: `src/undercover/texts.py`
- Modify: `src/undercover/bot/lobby_view.py`
- Modify: `src/undercover/bot/routers/lobby.py`
- Test: `tests/test_lobby_rules.py`, `tests/test_lobby_view.py`, `tests/test_lobby_router.py`, `tests/test_engine.py`

**Interfaces:**
- Produces:
  - `models`: `DEFAULT_TURN_SECONDS: Final = 45`, `TURN_CHOICES: Final = (30, 45, 60, 0)`, `LobbyState.turn_seconds`, `GameSessionState.turn_seconds`, `GameSessionState.turn_deadline: datetime | None`
  - `lobby`: `cycle_turn_seconds(lobby) -> None`
  - `engine`: `create_session(..., turn_seconds: int = 0)`
  - `texts`: `Buttons.TURN_LIMIT`, `Buttons.TURN_OFF`
  - `lobby_view`: кнопка `LobbyAction.TURN` в клавиатуре состава
  - `routers/lobby`: обработчик `TURN`, `turn_seconds` уезжает в `create_session`

- [ ] **Step 1: Написать падающие тесты**

В `tests/test_lobby_rules.py`:

```python
from undercover.game.lobby import cycle_turn_seconds
from undercover.game.models import DEFAULT_TURN_SECONDS, TURN_CHOICES


def test_a_new_lobby_starts_at_the_default_turn_length() -> None:
    assert lobby().turn_seconds == DEFAULT_TURN_SECONDS


def test_the_turn_length_walks_every_choice_and_comes_back() -> None:
    state = lobby()
    seen = []
    for _ in range(len(TURN_CHOICES)):
        cycle_turn_seconds(state)
        seen.append(state.turn_seconds)

    assert sorted(seen) == sorted(TURN_CHOICES)
    assert state.turn_seconds == DEFAULT_TURN_SECONDS


def test_an_unknown_turn_length_falls_back_to_the_first_choice() -> None:
    state = lobby(turn_seconds=999)

    cycle_turn_seconds(state)

    assert state.turn_seconds == TURN_CHOICES[0]
```

В `tests/test_lobby_view.py` — кнопка показывает текущее значение и «без таймера» на нуле:

```python
def test_the_turn_button_shows_the_current_length() -> None:
    assert Buttons.TURN_LIMIT.format(seconds=DEFAULT_TURN_SECONDS) in texts_of(lobby(2))


def test_the_turn_button_says_plainly_when_the_timer_is_off() -> None:
    assert Buttons.TURN_OFF in texts_of(lobby(2, turn_seconds=0))
```

В `tests/test_lobby_router.py` — значение доезжает до сессии:

```python
async def test_the_chosen_turn_length_reaches_the_session(group: Group) -> None:
    await group.command("/game")
    await group.press(Buttons.JOIN_LOBBY, user_id=GUEST_ID)
    await group.press(Buttons.JOIN_LOBBY, user_id=OTHER_ID)

    await group.press(Buttons.TURN_LIMIT.format(seconds=DEFAULT_TURN_SECONDS))
    chosen = group.lobbies.stored.turn_seconds

    await group.press(Buttons.PLAY)

    assert group.games.stored.turn_seconds == chosen
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `poetry run pytest tests/test_lobby_rules.py tests/test_lobby_view.py -q`
Expected: FAIL — `ImportError: cannot import name 'DEFAULT_TURN_SECONDS'`

- [ ] **Step 3: Дополнить модели**

В `game/models.py` над `LobbyState`:

```python
DEFAULT_TURN_SECONDS: Final = 45
TURN_CHOICES: Final = (30, 45, 60, 0)
```

(добавить `Final` в импорт из `typing`)

В `LobbyState` — поле после `category_ids`:

```python
    turn_seconds: int = Field(default=DEFAULT_TURN_SECONDS, ge=0)
```

В `GameSessionState` — поля после `mode`:

```python
    turn_seconds: int = Field(default=0, ge=0)

    turn_deadline: datetime | None = None
```

Умолчание `0` в сессии значит «без таймера» и оставляет hot-seat таким, как был.

- [ ] **Step 4: Дописать правило и движок**

В `game/lobby.py`:

```python
def cycle_turn_seconds(lobby: LobbyState) -> None:
    position = (
        TURN_CHOICES.index(lobby.turn_seconds) + 1 if lobby.turn_seconds in TURN_CHOICES else 0
    )
    lobby.turn_seconds = TURN_CHOICES[position % len(TURN_CHOICES)]
```

В `game/engine.py` — `create_session` получает `turn_seconds: int = 0` и кладёт его в `GameSessionState(...)`.

- [ ] **Step 5: Дописать тексты и клавиатуру**

В `Buttons`:

```python
    TURN_LIMIT: Final = "Ход: {seconds} с"
    TURN_OFF: Final = "Ход: без таймера"
```

В `lobby_view.py` добавить `TURN = "turn"` в `LobbyAction` и третью кнопку в ряд настроек:

```python
    settings.append(_lobby_button(_turn_label(lobby.turn_seconds), LobbyAction.TURN))
```

```python
def _turn_label(seconds: int) -> str:
    return Buttons.TURN_OFF if seconds <= 0 else Buttons.TURN_LIMIT.format(seconds=seconds)
```

Ряд настроек может стать трёхкнопочным — это нормально, тексты короткие.

- [ ] **Step 6: Дописать обработчик и прокинуть значение**

В `create_lobby_router` — обработчик по образцу `cb_spies`, вызывающий `cycle_turn_seconds`. В `cb_play` добавить в `create_session(...)` аргумент `turn_seconds=lobby.turn_seconds`.

- [ ] **Step 7: Прогнать проверки**

Run: `poetry run ruff check . && poetry run mypy && poetry run pytest -m "not integration" -q`
Expected: PASS

---

## Task 19: Часовой хода

**Files:**
- Create: `src/undercover/bot/turn_clock.py`
- Modify: `src/undercover/texts.py`
- Test: `tests/test_turn_clock.py` (create), `tests/test_texts.py` (modify)

**Interfaces:**
- Consumes: `GameSessionState.turn_seconds`, `turn_deadline` (Task 18)
- Produces:
  - `Turn(session_id: str, round: int, cursor: int)` — frozen dataclass
  - `TurnView(caption: str, keyboard: InlineKeyboardMarkup)` — frozen dataclass
  - `OnExpire = Callable[[Bot, Turn], Awaitable[None]]`
  - `TurnClock(tick: timedelta = TICK)` с `start(bot, state, view, on_expire) -> None`, `stop(session_id) -> None`, `shutdown() -> None`, свойством `running: frozenset[str]`
  - `timed_caption(base: str, seconds_left: int, total: int) -> str`
  - `texts.countdown_line(seconds_left: int, total: int) -> str`, класс `Timer`

- [ ] **Step 1: Написать падающие тесты**

Создать `tests/test_turn_clock.py`:

```python
import asyncio
from datetime import UTC, datetime, timedelta
from typing import Final

from aiogram.methods import EditMessageCaption
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from fake_bot import CHAT_ID, HOST_ID, FakeSession, make_bot
from undercover.bot.turn_clock import Turn, TurnClock, TurnView, timed_caption
from undercover.game.models import GameMode, GameSessionState, GameStatus, PlayerState
from undercover.texts import Timer, countdown_line

SESSION_ID: Final = "11111111-1111-1111-1111-111111111111"
VIEW: Final = TurnView(
    caption="Говорит: Аня",
    keyboard=InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Дальше", callback_data="x")]]
    ),
)


def make_state(turn_seconds: float = 0.3) -> GameSessionState:
    return GameSessionState(
        session_id=SESSION_ID,
        chat_id=CHAT_ID,
        host_user_id=HOST_ID,
        mode=GameMode.GROUP,
        status=GameStatus.DISCUSSION,
        players=[PlayerState(order_index=0, name="Аня", is_spy=True)],
        word_id=1,
        word_text="пицца",
        discussion_order=[0],
        current_message_id=500,
        turn_seconds=int(turn_seconds) or 1,
        turn_deadline=datetime.now(UTC) + timedelta(seconds=turn_seconds),
    )


class Expiries:
    def __init__(self) -> None:
        self.turns: list[Turn] = []
        self.done = asyncio.Event()

    async def __call__(self, bot: object, turn: Turn) -> None:
        self.turns.append(turn)
        self.done.set()


async def test_the_turn_expires_with_the_round_and_cursor_it_started_on() -> None:
    clock = TurnClock(tick=timedelta(seconds=0.05))
    expiries = Expiries()
    state = make_state()
    state.discussion_round = 3
    state.discussion_cursor = 2

    clock.start(make_bot(FakeSession()), state, VIEW, expiries)
    await asyncio.wait_for(expiries.done.wait(), timeout=2)

    assert expiries.turns == [Turn(session_id=SESSION_ID, round=3, cursor=2)]


async def test_the_countdown_is_repainted_while_the_turn_runs() -> None:
    session = FakeSession()
    clock = TurnClock(tick=timedelta(seconds=0.05))
    expiries = Expiries()

    clock.start(make_bot(session), make_state(), VIEW, expiries)
    await asyncio.wait_for(expiries.done.wait(), timeout=2)

    repaints = session.calls(EditMessageCaption)
    assert repaints
    assert all(call.reply_markup == VIEW.keyboard for call in repaints)
    assert all(VIEW.caption in (call.caption or "") for call in repaints)


async def test_a_turn_without_a_timer_starts_no_task_at_all() -> None:
    session = FakeSession()
    clock = TurnClock()
    state = make_state()
    state.turn_seconds = 0
    state.turn_deadline = None

    clock.start(make_bot(session), state, VIEW, Expiries())

    assert clock.running == frozenset()
    assert session.requests == []


async def test_starting_a_new_turn_cancels_the_previous_one() -> None:
    clock = TurnClock(tick=timedelta(seconds=0.05))
    expiries = Expiries()
    bot = make_bot(FakeSession())

    clock.start(bot, make_state(turn_seconds=5), VIEW, expiries)
    clock.start(bot, make_state(), VIEW, expiries)
    await asyncio.wait_for(expiries.done.wait(), timeout=2)
    await asyncio.sleep(0.05)

    assert len(expiries.turns) == 1


async def test_stop_silences_the_clock() -> None:
    clock = TurnClock(tick=timedelta(seconds=0.05))
    expiries = Expiries()

    clock.start(make_bot(FakeSession()), make_state(), VIEW, expiries)
    clock.stop(SESSION_ID)
    await asyncio.sleep(0.5)

    assert expiries.turns == []
    assert clock.running == frozenset()


async def test_shutdown_leaves_nothing_running() -> None:
    clock = TurnClock(tick=timedelta(seconds=0.05))

    clock.start(make_bot(FakeSession()), make_state(turn_seconds=5), VIEW, Expiries())
    await clock.shutdown()

    assert clock.running == frozenset()


def test_the_countdown_bar_empties_as_time_runs_out() -> None:
    full = countdown_line(60, 60)
    half = countdown_line(30, 60)
    empty = countdown_line(0, 60)

    assert full.count("▰") > half.count("▰") > empty.count("▰")
    assert "60" in full and "30" in half


def test_a_caption_without_a_timer_stays_untouched() -> None:
    assert timed_caption("Говорит: Аня", seconds_left=0, total=0) == "Говорит: Аня"


def test_a_timed_caption_carries_the_countdown_on_its_own_line() -> None:
    result = timed_caption("Говорит: Аня", seconds_left=30, total=60)

    assert result.startswith("Говорит: Аня\n")
    assert countdown_line(30, 60) in result
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `poetry run pytest tests/test_turn_clock.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'undercover.bot.turn_clock'`

- [ ] **Step 3: Дописать тексты**

В `texts.py`:

```python
class Timer:
    COUNTDOWN: Final = "{bar}  {seconds} с"
    SPENT: Final = "Время: {seconds} с"
    EXPIRED: Final = "Время вышло"
```

и функция рядом с `empty_catalog_text`:

```python
BAR_CELLS: Final = 10
BAR_FULL: Final = "▰"
BAR_EMPTY: Final = "▱"


def countdown_line(seconds_left: int, total: int) -> str:
    filled = round(BAR_CELLS * seconds_left / total) if total > 0 else 0
    return Timer.COUNTDOWN.format(
        bar=BAR_FULL * filled + BAR_EMPTY * (BAR_CELLS - filled), seconds=seconds_left
    )
```

`Timer.SPENT` и `Timer.EXPIRED` намеренно безличные: имена приходят из Telegram, род игрока неизвестен.

- [ ] **Step 4: Создать `bot/turn_clock.py`**

```python
import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardMarkup

from undercover.game.models import GameSessionState
from undercover.texts import countdown_line

logger = logging.getLogger(__name__)

TICK: Final = timedelta(seconds=5)


@dataclass(frozen=True, slots=True)
class Turn:
    session_id: str
    round: int
    cursor: int


@dataclass(frozen=True, slots=True)
class TurnView:
    caption: str
    keyboard: InlineKeyboardMarkup


OnExpire = Callable[[Bot, Turn], Awaitable[None]]


def timed_caption(base: str, seconds_left: int, total: int) -> str:
    if total <= 0:
        return base
    return f"{base}\n{countdown_line(seconds_left, total)}"


class TurnClock:
    def __init__(self, tick: timedelta = TICK) -> None:
        self._tick = tick
        self._tasks: dict[str, asyncio.Task[None]] = {}

    def start(
        self,
        bot: Bot,
        state: GameSessionState,
        view: TurnView,
        on_expire: OnExpire,
    ) -> None:
        self.stop(state.session_id)
        if state.turn_seconds <= 0 or state.turn_deadline is None:
            return

        session_id = state.session_id
        task = asyncio.create_task(
            self._run(bot, state.model_copy(deep=True), view, on_expire)
        )
        self._tasks[session_id] = task
        task.add_done_callback(lambda finished: self._forget(session_id, finished))

    def stop(self, session_id: str) -> None:
        task = self._tasks.pop(session_id, None)
        if task is not None:
            task.cancel()

    async def shutdown(self) -> None:
        tasks = list(self._tasks.values())
        self._tasks.clear()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    @property
    def running(self) -> frozenset[str]:
        return frozenset(self._tasks)

    async def _run(
        self,
        bot: Bot,
        state: GameSessionState,
        view: TurnView,
        on_expire: OnExpire,
    ) -> None:
        turn = Turn(
            session_id=state.session_id,
            round=state.discussion_round,
            cursor=state.discussion_cursor,
        )
        deadline = state.turn_deadline
        if deadline is None:
            return

        while True:
            left = deadline - datetime.now(UTC)
            if left <= timedelta(0):
                break
            await asyncio.sleep(min(self._tick, left).total_seconds())
            remaining = deadline - datetime.now(UTC)
            if remaining > timedelta(0):
                await self._repaint(bot, state, view, remaining)

        await on_expire(bot, turn)

    async def _repaint(
        self,
        bot: Bot,
        state: GameSessionState,
        view: TurnView,
        left: timedelta,
    ) -> None:
        if state.current_message_id is None:
            return
        try:
            await bot.edit_message_caption(
                chat_id=state.chat_id,
                message_id=state.current_message_id,
                caption=timed_caption(
                    view.caption, int(left.total_seconds()), state.turn_seconds
                ),
                reply_markup=view.keyboard,
            )
        except TelegramAPIError as error:
            logger.info("отсчёт партии %s не перерисовался (%s)", state.session_id, error)

    def _forget(self, session_id: str, finished: asyncio.Task[None]) -> None:
        if self._tasks.get(session_id) is finished:
            del self._tasks[session_id]
        if not finished.cancelled() and finished.exception() is not None:
            logger.exception(
                "часовой партии %s упал", session_id, exc_info=finished.exception()
            )
```

`reply_markup=view.keyboard` обязателен: `editMessageCaption` без него снимает клавиатуру, и ход остался бы без кнопок.

- [ ] **Step 5: Прогнать проверки**

Run: `poetry run ruff check . && poetry run mypy && poetry run pytest -m "not integration" -q`
Expected: PASS

---

## Task 20: Отсчёт и автопереход в обсуждении

**Files:**
- Modify: `src/undercover/bot/boards.py` (в `close_turn` добавляется клавиатура)
- Modify: `src/undercover/bot/routers/discussion.py`
- Modify: `src/undercover/bot/routers/finale.py` (гасить часового на финале)
- Modify: `src/undercover/bot/dispatcher.py`
- Test: `tests/test_boards.py`, `tests/test_discussion.py`, `tests/test_finale.py`, `tests/test_dispatcher.py`

**Interfaces:**
- Consumes: `TurnClock`, `TurnView`, `Turn`, `timed_caption` (Task 19); `KeyedLocks` (Task 17)
- Produces:
  - `DiscussionBoard.close_turn(bot, state, caption, keyboard: InlineKeyboardMarkup | None = None) -> None`
  - `create_discussion_router(clock: TurnClock, locks: KeyedLocks) -> Router`
  - `open_turn(bot, games, state, cursor, clock) -> None`
  - `close_turn(bot, state, marker: str, keyboard=None) -> None`
  - `expiry_handler(games, locks, clock) -> OnExpire`
  - `start_discussion` остаётся `PhaseStarter`-совместимой через `functools.partial(start_discussion, clock=clock)` в `dispatcher.py`

- [ ] **Step 1: Написать падающие тесты**

В `tests/test_boards.py`:

```python
async def test_a_frozen_turn_can_keep_its_buttons_when_the_round_is_over() -> None:
    session = FakeSession()

    await FeedBoard().close_turn(
        make_bot(session), make_state(GameMode.GROUP), "Говорит: Аня", KEYBOARD
    )

    (frozen,) = session.calls(EditMessageCaption)
    assert frozen.reply_markup == KEYBOARD
```

В `tests/test_discussion.py`:

```python
async def test_a_timed_group_turn_shows_the_countdown_from_the_first_frame(
    table: Table,
) -> None:
    state = make_state(mode=GameMode.GROUP, turn_seconds=60)
    await table.games.save(state)

    await start_discussion(table.bot, table.games, state, clock=table.clock)

    assert countdown_line(60, 60) in table.card.caption
    assert table.games.stored.turn_deadline is not None


async def test_pressing_next_reports_the_time_the_speaker_took(table: Table) -> None:
    state = make_state(mode=GameMode.GROUP, turn_seconds=60)
    await table.games.save(state)
    await start_discussion(table.bot, table.games, state, clock=table.clock)

    await table.press(Buttons.NEXT_SPEAKER)

    (frozen,) = table.session.calls(EditMessageCaption)
    assert Timer.SPENT.format(seconds=0) in (frozen.caption or "")


async def test_an_expired_turn_moves_on_by_itself(table: Table) -> None:
    state = make_state(mode=GameMode.GROUP, turn_seconds=60)
    await table.games.save(state)
    on_expire = expiry_handler(table.games, table.locks, table.clock)
    await start_discussion(
        table.bot, table.games, state, clock=table.clock, on_expire=on_expire
    )
    opened = table.games.stored

    await on_expire(
        table.bot, Turn(SESSION_ID, opened.discussion_round, opened.discussion_cursor)
    )

    assert table.games.stored.discussion_cursor == 1
    assert any(
        Timer.EXPIRED in (call.caption or "")
        for call in table.session.calls(EditMessageCaption)
    )


async def test_an_expired_last_turn_keeps_the_round_buttons(table: Table) -> None:
    state = make_state(mode=GameMode.GROUP, turn_seconds=60)
    await table.games.save(state)
    on_expire = expiry_handler(table.games, table.locks, table.clock)
    await start_discussion(
        table.bot, table.games, state, clock=table.clock, on_expire=on_expire
    )
    last = len(NAMES) - 1
    stored = table.games.stored
    stored.discussion_cursor = last
    await table.games.save(stored)

    await on_expire(table.bot, Turn(SESSION_ID, stored.discussion_round, last))

    frozen = table.session.calls(EditMessageCaption)[-1]
    assert frozen.reply_markup is not None
    assert Buttons.ANOTHER_ROUND in [
        item.text for row in frozen.reply_markup.inline_keyboard for item in row
    ]
    assert table.games.stored.discussion_cursor == last


async def test_a_stale_tick_is_ignored(table: Table) -> None:
    state = make_state(mode=GameMode.GROUP, turn_seconds=60, discussion_cursor=2)
    state.discussion_order = list(range(len(NAMES)))
    await table.games.save(state)
    on_expire = expiry_handler(table.games, table.locks, table.clock)

    await on_expire(table.bot, Turn(SESSION_ID, round=1, cursor=0))

    assert table.games.stored.discussion_cursor == 2


async def test_a_button_and_an_expiry_racing_move_the_turn_exactly_once(
    table: Table,
) -> None:
    state = make_state(mode=GameMode.GROUP, turn_seconds=60)
    await table.games.save(state)
    on_expire = expiry_handler(table.games, table.locks, table.clock)
    await start_discussion(
        table.bot, table.games, state, clock=table.clock, on_expire=on_expire
    )
    stored = table.games.stored
    opened = len(table.session.calls(SendPhoto))

    await asyncio.gather(
        on_expire(
            table.bot, Turn(SESSION_ID, stored.discussion_round, stored.discussion_cursor)
        ),
        table.press(Buttons.NEXT_SPEAKER),
    )

    assert len(table.session.calls(SendPhoto)) == opened + 1
    assert table.games.stored.discussion_cursor == 1
```

Харнесс `Table` в `tests/discussion_harness.py` дополнить полями `clock: TurnClock` и
`locks: KeyedLocks`, а `make_state` — параметром `turn_seconds: int = 0`. Часовой в
харнессе собирается как `TurnClock(tick=timedelta(seconds=0.05))`, чтобы тесты, где
он действительно тикает, не ждали пять секунд.

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `poetry run pytest tests/test_discussion.py tests/test_boards.py -q`
Expected: FAIL — `start_discussion() got an unexpected keyword argument 'clock'`

- [ ] **Step 3: Дать `close_turn` клавиатуру**

В `bot/boards.py` во всех трёх местах (`Protocol`, `SingleCardBoard`, `FeedBoard`) сигнатура становится:

```python
    async def close_turn(
        self,
        bot: Bot,
        state: GameSessionState,
        caption: str,
        keyboard: InlineKeyboardMarkup | None = None,
    ) -> None: ...
```

`FeedBoard` передаёт `reply_markup=keyboard` вместо `reply_markup=None`. Умолчание `None` сохраняет прежнее поведение: обычный ход замерзает без кнопок.

- [ ] **Step 4: Провести часового через обсуждение**

`open_turn` ставит дедлайн, шлёт карточку с отсчётом и заводит часового:

```python
async def open_turn(
    bot: Bot,
    games: GameStateRepository,
    state: GameSessionState,
    cursor: int,
    clock: TurnClock,
    on_expire: OnExpire,
) -> None:
    name = state.players[state.discussion_order[cursor]].name
    is_last = cursor == len(state.discussion_order) - 1
    image = await asyncio.to_thread(render_speaker_card, name)

    keyboard = _speaker_keyboard(state, cursor, is_last)
    base = speaker_caption(state, cursor)
    state.turn_deadline = _deadline(state)

    message_id = await board_for(state).open_turn(
        bot,
        state,
        as_photo(image, f"speaker_{cursor}.{CARD_SUFFIX}"),
        timed_caption(base, state.turn_seconds, state.turn_seconds),
        keyboard,
    )

    state.discussion_cursor = cursor
    state.current_message_id = message_id
    await games.save(state)

    clock.start(bot, state, TurnView(caption=base, keyboard=keyboard), on_expire)
```

`on_expire` приходит сверху, а не собирается внутри: иначе `open_turn` тащил бы за
собой `locks` и замкнулся бы на `expiry_handler`, который сам его вызывает.
`create_discussion_router` строит `on_expire = expiry_handler(games, locks, clock)`
один раз и передаёт во все вызовы.

```python
def _deadline(state: GameSessionState) -> datetime | None:
    if state.turn_seconds <= 0:
        return None
    return datetime.now(UTC) + timedelta(seconds=state.turn_seconds)


def _spent(state: GameSessionState) -> str:
    if state.turn_seconds <= 0 or state.turn_deadline is None:
        return ""
    left = max(0, int((state.turn_deadline - datetime.now(UTC)).total_seconds()))
    return Timer.SPENT.format(seconds=state.turn_seconds - left)


async def close_turn(
    bot: Bot,
    state: GameSessionState,
    marker: str,
    keyboard: InlineKeyboardMarkup | None = None,
) -> None:
    base = speaker_caption(state, state.discussion_cursor)
    caption = f"{base}\n{marker}" if marker else base
    await board_for(state).close_turn(bot, state, caption, keyboard)
```

- [ ] **Step 5: Написать обработчик истечения**

```python
def expiry_handler(
    games: GameStateRepository, locks: KeyedLocks, clock: TurnClock
) -> OnExpire:
    async def on_expire(bot: Bot, turn: Turn) -> None:
        async with locks.held(turn.session_id):
            state = await games.load(turn.session_id)
            if state is None or state.status is not GameStatus.DISCUSSION:
                return
            if (state.discussion_round, state.discussion_cursor) != (turn.round, turn.cursor):
                return

            next_cursor = state.discussion_cursor + 1
            if next_cursor >= len(state.discussion_order):
                await close_turn(
                    bot,
                    state,
                    Timer.EXPIRED,
                    _speaker_keyboard(state, state.discussion_cursor, is_last=True),
                )
                return

            await close_turn(bot, state, Timer.EXPIRED)
            await open_turn(bot, games, state, next_cursor, clock, on_expire)

    return on_expire
```

Круг, закончившийся по таймеру, сохраняет клавиатуру — иначе «Ещё круг» и «Раскрыть карты» исчезли бы вместе с ходом и партия встала бы намертво.

- [ ] **Step 6: Обновить места вызова и обернуть кнопки блокировкой**

Все вызовы из Task 9 меняются:

| Было (Task 9) | Стало |
|---|---|
| `await close_turn(bot, state)` в `cb_next_speaker` | `await close_turn(bot, state, _spent(state))` |
| `await close_turn(bot, state)` в `cb_another_round` | `await close_turn(bot, state, _spent(state))` |
| `await open_turn(bot, games, state, cursor)` | `await open_turn(bot, games, state, cursor, clock, on_expire)` |
| `start_discussion(bot, games, state)` | `start_discussion(bot, games, state, clock, on_expire)` |

`cb_next_speaker` и `cb_another_round` целиком заворачиваются в
`async with locks.held(callback_data.session_id):` — от загрузки состояния до
`open_turn`. Иначе тик и нажатие успевают продвинуть ход дважды.

- [ ] **Step 7: Гасить часового на финале**

В `finale.py` в `cb_show_spies` и `cb_new_game` вызвать `clock.stop(state.session_id)`; в `cb_play_again` — `clock.stop(старая сессия)` перед стартом новой. `create_finale_router` получает параметр `clock: TurnClock`. В `cb_play_again` для `GameMode.GROUP` вместо `start_reveal` идут `deliver_roles` и `start_discussion`; `mode`, `turn_seconds` и `user_id` переносятся из прошлой сессии через `player_ids` и `mode` у `create_session`.

- [ ] **Step 8: Проводка**

В `dispatcher.py`:

```python
    clock = TurnClock()
    locks = KeyedLocks()

    dispatcher.include_router(create_discussion_router(clock, locks))
    dispatcher.include_router(create_finale_router(open_words, log_game, clock))
    dispatcher.shutdown.register(clock.shutdown)
```

`start_discussion` теперь принимает `clock` и `on_expire`, а `PhaseStarter` их не знает — связать через `functools.partial`, собрав `on_expire = expiry_handler(dependencies.games, locks, clock)` рядом с `clock`:

```python
    begin_discussion = partial(start_discussion, clock=clock, on_expire=on_expire)
    dispatcher.include_router(create_lobby_router(open_words, begin_discussion))
    dispatcher.include_router(create_reveal_router(begin_discussion))
```

- [ ] **Step 9: Прогнать проверки**

Run: `poetry run ruff check . && poetry run ruff format --check . && poetry run mypy && poetry run pytest -q`
Expected: PASS

---

## Task 21: README о таймере и финальная сверка

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Дописать про таймер**

Кнопка «Ход» в лобби переключает 30/45/60 секунд и «без таймера». Отсчёт живёт в карточке говорящего и обновляется раз в пять секунд — чаще нельзя, Telegram ограничивает правки примерно двадцатью в минуту на чат. По истечении ход уходит к следующему сам; закончившийся ход остаётся в чате отчётом.

- [ ] **Step 2: Записать принятые ограничения**

Одним абзацем, чтобы они не потерялись вместе со спеком: бот рассчитан на один экземпляр (часовой и блокировки живут в процессе); после перезапуска отсчёт замолкает, но кнопки остаются и партия доигрывается вручную; присоединиться к идущей партии нельзя.

- [ ] **Step 3: Финальная сверка**

Run: `poetry run poetry check --lock && poetry run ruff check . && poetry run ruff format --check . && poetry run mypy && poetry run pytest`
Expected: PASS, покрытие не ниже 90% строк и 85% ветвей.

Прочитать глазами: во всех новых текстах бренд `Undercover`, эмодзи нет, обращение на «вы», род игроков нигде не угадывается.
