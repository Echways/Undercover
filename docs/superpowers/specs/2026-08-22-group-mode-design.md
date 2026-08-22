# Групповой режим Undercover: лобби, раздача ролей в ЛС, таймер хода

Дата: 2026-08-22. Статус: согласовано, готово к плану.

## 1. Зачем

Сейчас бот умеет один сценарий — hot-seat: телефон ведущего ходит по кругу,
имена вводятся руками, вся партия живёт в одном сообщении. Это работает только
на одной физической тусовке.

Групповой режим снимает оба ограничения: ведущий открывает лобби в группе,
игроки жмут «Я в игре», бот присылает каждому его карточку в личку. Имена
подтягиваются из Telegram, телефон никому не передаётся, играть можно удалённо.

Таймер хода добавляет тексто́вой игре то, чего ей не хватает, — темп. Живой
обратный отсчёт в карточке говорящего, автопереход к следующему по истечении.

Hot-seat остаётся как есть и работает параллельно, включая игру в группе с
одного телефона.

## 2. Принятые решения

| Решение                                                                                                              | Основание                                                                                                                                                                                                                                                                                                                         |
| --------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Лобби — отдельная модель и отдельный ключ Redis, не`GameSessionState`                | У лобби другой жизненный цикл и другой набор полей: нет слова и ролей, зато есть черновик настроек.`GameSessionState` рождается уже готовым через существующий `create_session()`                                  |
| Лобби ключуется по`chat_id`, а не по UUID                                                            | Лобби в чате всегда одно. В`callback_data` вместо 36-символьного UUID ложатся 14 символов — при лимите в 64 байта это запас                                                                                                                                 |
| Лобби — текстовое сообщение, не карточка                                                  | Перерисовывается на каждое присоединение; гонять Pillow и upload по 16 раз дорого. Карточки остаются там, где нужны, — роли и говорящий                                                                                                   |
| «Я в игре» — callback, не URL-кнопка                                                                       | Один тап для всех, кто уже открывал бота.`TelegramForbiddenError` → `callback.answer(url=<deep-link>)`, и клиент сам открывает бота — авто-редирект только для новичков                                                                          |
| Число шпионов и длительность хода — кнопки-циклеры                               | Убирает целые экраны настроек: отдельный вид клавиатуры нужен только категориям                                                                                                                                                                                       |
| Категории показываются целиком, по две в ряд, без пагинации                | Листалка по шесть штук из hot-seat в группе только мешает                                                                                                                                                                                                                                          |
| Раздача ролей идёт**до** удаления лобби                                                | Если карточка не дошла шпиону, партия мертва, а игроки этого не знают. Старт откатывается целиком                                                                                                                                                          |
| Ветвление по режиму — одна функция`board_for(state)`                                         | Роутер-близнец нарушил бы DRY, россыпь`if mode` по `discussion.py` — SRP                                                                                                                                                                                                                               |
| Часовой = дедлайн в состоянии + задача-будильник                                     | Корректность держится на идемпотентности тика, а не на механизме сна. Опросный цикл по Redis добавил бы только переживание рестарта, а после рестарта у партии остаются рабочие кнопки |
| Тик отсчёта — 5 секунд                                                                                     | Лимит Telegram ~20 правок/мин на чат. 12 правок на минутный ход держат запас втрое                                                                                                                                                                                                   |
| Гонки закрываются`KeyedLocks` в процессе                                                         | Атомарный CAS Lua-скриптом поверх JSON-состояния — плохая сделка ради поддержки нескольких нод, которых нет                                                                                                                                               |
| Тексты кнопок без эмодзи, существующие константы переиспользуются | Общий стиль проекта: короткие фразы обычным предложением                                                                                                                                                                                                                                  |

## 3. Модель данных

### 3.1 Дополнения к существующему (`game/models.py`)

```python
class GameMode(StrEnum):
    HOT_SEAT = "hot_seat"
    GROUP = "group"

```

`GameStatus` не трогается: лобби — не сессия, и статуса `LOBBY` в ней быть не
должно.

`PlayerState` получает `user_id: int | None = None` — `None` в hot-seat.

`GameSessionState` получает:

- `mode: GameMode = GameMode.HOT_SEAT`
- `turn_seconds: int = Field(default=0, ge=0)` — `0` значит «без таймера»
- `turn_deadline: datetime | None = None`

Значения по умолчанию подобраны так, что уже лежащие в Redis сессии
десериализуются без миграции.

### 3.2 Лобби (`game/models.py`)

```python
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
    turn_seconds: int = Field(default=DEFAULT_TURN_SECONDS, ge=0)
    view: LobbyView = LobbyView.ROSTER
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
```

Список категорий для клавиатуры в состоянии не хранится — он читается из
каталога при отрисовке вида `CATEGORIES`. Иначе снимок каталога протухает и
дублирует источник правды.

### 3.3 Правила лобби (`game/lobby.py`, новый)

`DEFAULT_TURN_SECONDS: Final = 45` и `TURN_CHOICES: Final = (30, 45, 60, 0)`
объявляются в `game/models.py`, рядом с полем, которому служат умолчанием, —
иначе `models` и `lobby` ссылались бы друг на друга.

Чистые функции без Telegram, тестируются в изоляции:

```python
def join(lobby: LobbyState, player: LobbyPlayer) -> None
def leave(lobby: LobbyState, user_id: int) -> None
def cycle_spies_count(lobby: LobbyState) -> None
def cycle_turn_seconds(lobby: LobbyState) -> None
def toggle_category(lobby: LobbyState, category_id: int) -> None
def ensure_playable(lobby: LobbyState) -> None
```

`join` поднимает `GameRulesError` на дубль и на переполнение (`MAX_PLAYERS`).
`leave` и `cycle_spies_count` держат инвариант
`1 <= spies_count <= max_spies_count(len(players))`: после ухода игрока число
шпионов клампится вниз. `ensure_playable` — проверка перед стартом
(`MIN_PLAYERS <= len(players)`).

### 3.4 Движок (`game/engine.py`)

Единственная правка: `assign_roles` и `create_session` получают необязательный
`player_ids: Sequence[int] | None = None`, который раскладывается по
`PlayerState.user_id`. Без него роутеру пришлось бы знать, что `assign_roles`
сохраняет порядок имён, — хрупкое неявное знание.

### 3.5 Репозиторий (`redis/lobby_state.py`, новый)

`LobbyRepository` — близнец `GameStateRepository`: тот же TTL, тот же приём с
Lua-скриптом на снятие активного ключа.

```
lobby:<chat_id>              — состояние
chat_active_lobby:<chat_id>  — маркер активного лобби в чате
```

Добавляется в `AppDependencies` рядом с `games` и в `as_workflow_data()`.

## 4. Лобби в группе

Роутер `bot/routers/lobby.py`.

### 4.1 Сообщение

```
Undercover — набор в партию.

В игре (3 из 16):
1. Аня
2. Борис
3. Влад

Игроков: 3, из них шпионов: 1.
Слова: весь словарь.
Ход: 45 секунд.

Жмите «Я в игре» — слово придёт в личку.
```

Клавиатура вида `ROSTER`:

```
[ Я в игре ]            [ Выйти из состава ]
[ Шпионов: 1 ]          [ Категории ]
[ Ход: 45 с ]
[ Начать партию ]
```

Клавиатура вида `CATEGORIES` — все категории каталога по две в ряд, отмеченные
префиксом, плюс `[ Готово ]`.

`Начать партию` и `Категории` показываются всем, но нажимает только ведущий —
остальным `Errors.NOT_HOST`. Прятать кнопки нельзя: клавиатура одна на всех.

### 4.2 Callback

```python
class LobbyAction(StrEnum):
    JOIN = "join"
    LEAVE = "leave"
    SPIES = "spies"
    TURN = "turn"
    CATEGORIES = "cats"
    CATEGORY = "cat"
    DONE = "done"
    PLAY = "play"

class LobbyCB(CallbackData, prefix="lobby"):
    action: LobbyAction
    value: int = 0
```

`value` несёт `category_id` для `CATEGORY`, иначе игнорируется. `chat_id` в
данных кнопки не нужен — он и так приходит в `callback.message.chat.id`, и
`InaccessibleMessage` его тоже отдаёт.

### 4.3 Вход в лобби

`/game` в группе:

1. `games.load_active(chat_id)` не пуст → «В этом чате уже идёт партия».
2. Создаётся `LobbyState`, отправляется сообщение, `message_id` сохраняется.

`/game` в личке → подсказка, что режим групповой.

Нажатие «Я в игре»:

1. Игрок уже в составе → alert.
2. `join()` поднял `GameRulesError` → alert с текстом правила.
3. `bot.send_message(user_id, Lobby.DM_WELCOME)`:
   - `TelegramForbiddenError` → `callback.answer(url=deep_link)`, состав не
     меняется. Игрок нажимает Start в личке и попадает в тот же путь ниже;
   - успех → игрок добавлен, сообщение лобби перерисовано.

Deep-link: `create_start_link(bot, payload=f"join_{chat_id}", encode=False)`.
Payload `join_-1001234567890` укладывается в разрешённый Telegram набор
`[A-Za-z0-9_-]{1,64}`.

`/start join_<chat_id>` в личке (`bot/routers/start.py`): фильтр
`CommandStart(deep_link=True, magic=F.args.regexp(JOIN_PAYLOAD))`, из группы
`chat_id`, дальше тот же `join()` и перерисовка лобби в группе. Обычный
`/start` не трогается — в группе он по-прежнему открывает hot-seat.

### 4.4 Живучесть сообщения лобби

Если сообщение удалили из чата, правка падает `TelegramBadRequest`. В
`bot/message_utils.py` появляется `show_or_resend_text` — текстовый двойник
`show_or_advance_card`: пробует править, при неудаче шлёт новое и возвращает
`Message`, вызывающий обновляет `message_id`.

## 5. Старт партии и раздача ролей

Порядок операций защищает от партии, начатой вслепую:

```
ensure_playable
      ↓
create_session(..., player_ids=[p.user_id for p in lobby.players])
      ↓
deliver_roles(bot, state)  →  список игроков, до которых не дошло
      ↓
не пусто?  →  лобби на месте, сессия не сохранена, в группе:
              «Аня, откройте личку с ботом» + deep-link
      ↓
пусто?     →  games.save(state), lobbies.delete(chat_id),
              сообщение лобби превращается в «Партия началась. Роли — в личке»,
              start_discussion(bot, games, state)
```

В фазе 2 `start_discussion` и `_show_speaker` получают параметр `clock` — до
таймера его передавать нечему.

`bot/role_delivery.py` (новый):

```python
async def deliver_roles(bot: Bot, state: GameSessionState) -> list[PlayerState]
def render_role_card(player: PlayerState, state: GameSessionState) -> bytes
```

`render_role_card` переезжает сюда из `reveal.py` (там он был `_render_role_card`)
и импортируется обратно — рендер роли нужен обоим режимам.

Рассылка — `asyncio.gather` по 16 адресатам, рендер каждой карточки в
`asyncio.to_thread`. Глобальный лимит Telegram (~30 сообщений в секунду) при
шестнадцати не задевается, семафор не нужен.

## 6. Обсуждение в группе

### 6.1 Доска (`bot/boards.py`, новый)

`discussion.py` уже сведён так, что «править сообщение или слать новое»
решается в одном месте — `_show_speaker`. Туда входит стратегия:

```python
class DiscussionBoard(Protocol):
    async def open_turn(self, bot, state, photo, caption, keyboard) -> Message: ...
    async def close_turn(self, bot, state, summary: str) -> None: ...

def board_for(state: GameSessionState) -> DiscussionBoard
```

- `SingleCardBoard` — hot-seat: `open_turn` = существующий
  `show_or_advance_card`, `close_turn` ничего не делает;
- `FeedBoard` — группа: `close_turn` снимает клавиатуру с предыдущей карточки и
  дописывает к подписи строку отчёта, `open_turn` отправляет **новое**
  сообщение следующему говорящему.

`board_for` — единственное ветвление по режиму во всём обсуждении.

### 6.2 Права (`bot/guards.py`)

```python
def may_act(state: GameSessionState, user_id: int) -> bool
```

Ведущий может всё. В `GROUP` во время `DISCUSSION` «Дальше» может нажать ещё и
тот, чей сейчас ход, — партия не виснет на отошедшем ведущем. В остальных фазах
и в hot-seat говорящего нет, остаётся только ведущий. `load_game_in_phase`
вызывает `may_act` вместо нынешнего сравнения с `host_user_id`; новых
параметров не появляется, поведение целиком определяется `mode`.

### 6.3 Разгрузка `discussion.py`

Файл уже 313 строк и по этой задаче растёт с обеих сторон. Финальный экран —
самостоятельная ответственность (конец партии, журнал, «Ещё партия» / «Новый
состав»), поэтому `cb_show_spies`, `cb_play_again`, `cb_new_game` и
`_final_keyboard` переезжают в `bot/routers/finale.py`. Обсуждение остаётся
примерно на двухстах строках.

`cb_play_again` в `GROUP` не зовёт `start_reveal`: новая партия того же состава
проходит через `deliver_roles` и групповое обсуждение, `mode`, `turn_seconds` и
`user_id` переносятся из прошлой сессии.

## 7. Таймер хода

### 7.1 `bot/turn_clock.py` (новый)

```python
@dataclass(frozen=True, slots=True)
class Turn:
    session_id: str
    round: int
    cursor: int

OnExpire = Callable[[Bot, Turn], Awaitable[None]]
TICK: Final = timedelta(seconds=5)

class TurnClock:
    def __init__(self, tick: timedelta = TICK) -> None
    def start(self, bot: Bot, state: GameSessionState, on_expire: OnExpire) -> None
    def stop(self, session_id: str) -> None
    async def shutdown(self) -> None
```

Внутри — `dict[str, asyncio.Task[None]]`. `start` снимает прежнюю задачу этой
партии и заводит новую; при `turn_seconds == 0` просто снимает и выходит.
Обработчик истечения передаётся в `start`, а не в конструктор: иначе часовой и
`discussion.py` ссылались бы друг на друга.

`turn_deadline` пишет `_show_speaker` перед `games.save(state)` — у поля один
писатель. Задача только читает его.

Цикл задачи: спит до ближайшего из «следующий тик» и «дедлайн»; на тике правит
подпись через `edit_message_caption`; на дедлайне зовёт `on_expire`.
`TelegramBadRequest` на правке (сообщение удалили, подпись не изменилась)
логируется и не роняет задачу.

### 7.2 Идемпотентность

Тик несёт `(session_id, round, cursor)`. Обработчик истечения грузит состояние
и сверяет тройку: не совпало — ход уже сменился, тик протух, выходим молча.
Это же снимает гонку «игрок нажал „Дальше“ ровно в секунду истечения».

### 7.3 `utils/keyed_locks.py` (новый)

Сверки тройки мало: между `load` и `save` два корутина успевают прочитать
`cursor=2`, оба увидеть совпадение и оба продвинуть до 3 — в чат уйдут два
сообщения об одном говорящем. `KeyedLocks` — словарь `asyncio.Lock` с
рефкаунтом, ключ освобождается, когда последний ожидающий вышел:

```python
class KeyedLocks:
    @asynccontextmanager
    def held(self, key: str) -> AsyncIterator[None]: ...
```

Под ним идут смена хода (кнопка и истечение) и мутации лобби (вход из группы и
вход по deep-link из лички могут прийти одновременно).

### 7.4 Отсчёт в подписи

Подпись карточки говорящего:

```
Круг 2. Ход 3 из 5. Говорит: Влад
▰▰▰▰▰▰▱▱▱▱  35 с
```

Отчёт замороженного хода — та же подпись плюс `Время: 45 с` или
`Время вышло`. Формулировка нарочно безличная: имена приходят из Telegram, род
неизвестен, и «высказался/высказалась» угадывать нечем.

## 8. Тексты (`texts.py`)

Новые классы `Lobby` и `Timer`, `Buttons` дополняется. Стиль общий с проектом:
без эмодзи, короткие фразы обычным предложением, обращение на «вы».

Переиспользуются как есть: `Buttons.PLAY` («Начать партию»),
`Buttons.CATEGORIES_DONE` («Готово»), `Buttons.CHANGE_CATEGORIES`
(«Категории»), `Buttons.NEXT_SPEAKER`, `Buttons.ANOTHER_ROUND`,
`Buttons.SHOW_SPIES`, весь класс `Discussion`, `Errors.NOT_HOST`,
`Errors.STALE_TURN`, `empty_catalog_text`.

Добавляются:

```
Buttons.JOIN_LOBBY   = "Я в игре"
Buttons.LEAVE_LOBBY  = "Выйти из состава"
Buttons.SPIES_COUNT  = "Шпионов: {count}"
Buttons.TURN_LIMIT   = "Ход: {seconds} с"
Buttons.TURN_OFF     = "Ход: без таймера"

Timer.COUNTDOWN = "{bar}  {seconds} с"
Timer.SPENT     = "Время: {seconds} с"
Timer.EXPIRED   = "Время вышло"

Errors.LOBBY_CLOSED   = "Это лобби уже закрыто. Отправьте /game."
Errors.GAME_IN_CHAT   = "В этом чате уже идёт партия — сначала доиграйте её."
Errors.GROUP_ONLY     = "Так играют в группе: добавьте бота туда и отправьте /game."
```

`▰▱` в отсчёте — единственный декоративный знак и стоит в подписи, не на
кнопке.

## 9. Меню команд

`_publish_commands` публикует два набора: по умолчанию `/start`, а для
`BotCommandScopeAllGroupChats` — `/start` и `/game`. В личке команда, которая
работает только в группе, в меню не висит.

## 10. Краевые случаи

| Ситуация                                                                     | Поведение                                                                                                     |
| ------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------- |
| Лобби протухло по TTL, кнопку нажали                      | «Это лобби уже закрыто. Отправьте /game»                                                  |
| «Начать» нажал не ведущий                                      | `Errors.NOT_HOST`                                                                                                    |
| В составе меньше двух                                              | alert с текстом правила из`ensure_playable`                                                         |
| Игрок вышел, шпионов стало больше допустимого | `spies_count` клампится вниз молча                                                                 |
| Игрок вышел из группы во время партии                 | Партия идёт до конца; его карточка просто не откроется                    |
| `/game` при активной партии в чате                           | «В этом чате уже идёт партия»                                                                  |
| `/game` в личке                                                              | Подсказка, что режим групповой                                                               |
| Сообщение лобби удалили                                         | `show_or_resend_text` шлёт новое, `message_id` обновляется                                     |
| Каталог пуст                                                              | Существующий`empty_catalog_text`                                                                         |
| Бот перезапустился во время хода                         | Часовой замолкает, кнопки работают, партия доигрывается вручную |

Privacy mode групповому режиму не мешает: команды со слешем Telegram
доставляет боту и при включённом privacy. Hot-seat в группе по-прежнему требует
его выключить — там вводятся имена обычными сообщениями.

## 11. Принятые ограничения

- **Один инстанс бота.** `KeyedLocks` и `TurnClock` живут в процессе. При
  горизонтальном масштабировании потребуется CAS в Redis; сейчас его нет и не
  нужно.
- **Часовой не переживает рестарт.** `turn_deadline` в состоянии сохраняется,
  задача — нет. Деградация мягкая: кнопки на месте.
- **Категорий много — клавиатура длинная.** Пагинации в лобби нет сознательно.
- **Состав фиксируется на старте.** Присоединиться к идущей партии нельзя.

## 12. Тесты

Новые файлы: `test_lobby_rules.py`, `test_lobby_repository.py`,
`test_group_lobby.py`, `test_role_delivery.py`, `test_boards.py`,
`test_turn_clock.py`, `test_keyed_locks.py`, `test_finale.py`.

Расширяются: `test_discussion.py` (групповая ветка), `test_guards.py`
(`may_act`), `test_start.py` (deep-link), `test_engine.py` (`player_ids`),
`test_game_models.py`, `test_texts.py`, `test_dispatcher.py`.

`tests/fake_bot.py` дополняется `EditMessageCaption`, `EditMessageReplyMarkup`,
`GetMe` и фабрикой апдейта из личного чата.

Таймерные тесты гоняют реальный `asyncio` на коротких `turn_seconds` и
уменьшенном тике — подменять `sleep` не нужно, лишняя машинерия.

Порог покрытия CI держится: 90% строк, 85% ветвей.

## 13. Фазы

**Фаза 1 — лобби и раздача в ЛС.** Модель и правила лобби, `LobbyRepository`,
`player_ids` в движке, роутер лобби, deep-link, `show_or_resend_text`,
`role_delivery`, `boards`, `may_act`, вынос `finale.py`, меню команд, тексты.
Результат: групповая партия играется от начала до конца, без таймера.

**Фаза 2 — таймер хода.** `KeyedLocks`, `TurnClock`, отсчёт в подписи, отчёт
замороженного хода, автопереход, циклер длительности в лобби, тексты `Timer`.

Каждая фаза бьётся на пронумерованные шаги в плане реализации; шаги идут по
одному за промпт, каждый — со своими тестами.
