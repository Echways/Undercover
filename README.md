# Undercover
Telegram-бот для игры в шпиона на одном телефоне: 2–16 игроков, шпионов до
`игроков / 3`. Все получают одно слово, шпион — только подсказку к нему. Бот
собирает состав, показывает карточки по очереди, ведёт круги высказываний и
раскрывает роли. Вся партия живёт в одном сообщении, кнопки — у ведущего.

Стек: aiogram 3 и aiogram-dialog, Redis под состояние партий, PostgreSQL со
словарём (SQLAlchemy 2 + Alembic), карточки на Pillow.

## Запуск

Нужны Docker с Docker Compose и токен от [@BotFather](https://t.me/BotFather).
Для игры в группе там же выключите privacy mode:
`/mybots` → бот → Bot Settings → Group Privacy → Turn off.

```bash
cp .env.example .env                              # BOT_TOKEN и POSTGRES_PASSWORD
docker compose up -d --build                      # бот, PostgreSQL, Redis
docker compose run --rm bot alembic upgrade head  # схема базы
```

Дальше `/start`. Логи — `docker compose logs -f bot`, остановка —
`docker compose down` (`-v`, чтобы удалить данные).

## Конфигурация

Всё окружение — в `.env`, шаблон с пояснениями лежит в `.env.example`.
Неверное значение бот сообщает на старте и завершается с кодом 1.

| Переменная | Обязательна | Назначение |
|---|---|---|
| `BOT_TOKEN` | да | токен от @BotFather |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | да | учётные данные базы; их же берёт контейнер `postgres` |
| `POSTGRES_HOST` | да | `postgres` внутри compose, `localhost` при локальном запуске |
| `POSTGRES_PORT` | нет | `5432` по умолчанию |
| `REDIS_URL` | да | одна база под FSM aiogram и состояние партий |
| `LOG_LEVEL` | нет | `INFO` по умолчанию |

## Словарь

Слова в поставку не входят — миграции создают пустые таблицы, наполняет их
владелец бота. Пока слов нет, партия останавливается на «словарь игры пуст».
Три таблицы: `categories` (`slug`, `title`), `words` (`category_id`, `text`,
`difficulty` 1–3) и `spy_hints` (`word_id`, `hint_text`) — подсказка нужна хотя
бы одна.

```sql
WITH category AS (
    INSERT INTO categories (slug, title) VALUES ('food', 'Еда')
    RETURNING id
), word AS (
    INSERT INTO words (category_id, text, difficulty)
    SELECT id, 'борщ', 1 FROM category
    RETURNING id
)
INSERT INTO spy_hints (word_id, hint_text)
SELECT id, 'что-то горячее' FROM word;
```

Консоль: `docker compose exec postgres psql -U undercover -d undercover`.

`title` попадает на кнопку выбора, так что пишется по-человечески: «Еда», а не
`food`. Выбор бот предлагает, когда категорий с активными словами хотя бы две;
без отметок играет по всему словарю. Слово ищется в два шага — случайная
категория, затем случайное слово в ней, — поэтому большой раздел не вытесняет
маленький. Лишнее лучше выключать (`is_active = false`), а не удалять: журнал
партий ссылается на слова.

## Разработка

Нужны [Poetry](https://python-poetry.org/docs/#installation) 2.1+ и Python 3.13
или 3.14.

```bash
poetry install
docker compose up -d postgres redis
poetry run alembic upgrade head
poetry run undercover-bot
```

Конфигурация Alembic живёт в `[tool.alembic]` внутри `pyproject.toml`, а сами
миграции — в пакете (`src/undercover/db/migrations`), поэтому доступны в
контейнере без исходников: `docker compose run --rm bot alembic ...`.
Карточки можно посмотреть без бота: `poetry run python tools/card_preview.py`
раскладывает примеры экранов в `docs/preview`.

Те же команды гоняет CI (плюс порог покрытия: 90% строк, 85% ветвей):

```bash
poetry check --lock               # lock не разошёлся с pyproject
poetry run ruff check .           # линт
poetry run ruff format --check .  # форматирование
poetry run mypy                   # типы, strict
poetry run pytest                 # тесты; -m "not integration" — без Docker
```