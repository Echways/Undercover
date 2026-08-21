# Undercover

[![CI](https://github.com/Echways/undercover-game-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/Echways/undercover-game-bot/actions/workflows/ci.yml)

Telegram-бот для игры в шпиона с одного телефона.

Все игроки, кроме шпионов, получают одно и то же слово; шпиону достаётся только
подсказка. Телефон передаётся по кругу, каждый смотрит свою карточку, затем все
по очереди называют по одной ассоциации — и ищут того, кто выкручивается.

Ведущий собирает состав в диалоге с ботом — сколько игроков, сколько шпионов,
имена и, если словарь разбит на категории, откуда брать слово, — а дальше вся
партия живёт в одном сообщении: карточка сменяет карточку, чат не засоряется.

## Что нужно перед запуском

- Docker и Docker Compose.
- Токен бота от [@BotFather](https://t.me/BotFather): команда `/newbot`, имя и
  username бота — в ответ придёт строка вида `123456789:AA...`.

Для игры в группе выключите у бота privacy mode: в @BotFather
`/mybots → ваш бот → Bot Settings → Group Privacy → Turn off`. Иначе бот не
увидит сообщения с именами игроков.

## Запуск с нуля

```bash
cp .env.example .env          # вписать BOT_TOKEN и POSTGRES_PASSWORD
docker compose up -d --build  # поднять бота, PostgreSQL и Redis

docker compose run --rm bot alembic upgrade head  # схема базы
```

Схема приезжает пустой: слова и подсказки бот с собой не везёт, словарь
наполняет владелец бота — см. «База данных и словарь». Пока в базе нет ни
одного слова, первая же партия упрётся в «словарь игры не готов».

Готово — отправьте боту `/start`.

```bash
docker compose logs -f bot    # что происходит
docker compose down           # остановить
docker compose down -v        # остановить и стереть данные
```

## Переменные окружения

Все — в `.env`, список с пояснениями лежит в `.env.example`.

| Переменная | Обязательна | Назначение |
|---|---|---|
| `BOT_TOKEN` | да | токен от @BotFather |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | да | учётные данные базы; их же берёт контейнер `postgres` |
| `POSTGRES_HOST`, `POSTGRES_PORT` | нет | `postgres:5432` внутри compose, `localhost` при локальном запуске |
| `REDIS_URL` | да | одна база на FSM aiogram и на игровые сессии |
| `LOG_LEVEL` | нет | `INFO` по умолчанию |

Неверное окружение бот не переживает молча: он пишет, какое поле не подошло, и
завершается с кодом 1, не дожидаясь первой партии.

## Что где лежит

```
src/undercover/     пакет бота: игровая логика, роутеры, карточки, миграции
tests/              pytest: юнит-тесты и интеграционные на testcontainers
tools/              вспомогательные скрипты разработки, в образ не попадают
deploy/             Dockerfile и его .dockerignore
.github/            CI: workflow, составное действие, скрипты отчётов
pyproject.toml      Poetry: зависимости и настройки инструментов
poetry.lock         зафиксированные версии: те же в CI и в образе
docker-compose.yaml бот, PostgreSQL и Redis для локального запуска
```

Отдельного `alembic.ini` нет: конфигурация Alembic живёт в `[tool.alembic]`
внутри `pyproject.toml`, а сами миграции — в пакете
(`src/undercover/db/migrations`), поэтому они едут вместе с колесом и доступны
в контейнере без копирования исходников.

## База данных и словарь

Схема живёт в моделях SQLAlchemy (`src/undercover/db/models.py`) и
версионируется Alembic. Отдельного DSN в конфигурации нет — адрес базы берётся
из тех же переменных окружения, что и у бота.

```bash
alembic upgrade head                       # накатить схему
alembic downgrade base                     # откатить всё
alembic revision --autogenerate -m "..."   # новая миграция по изменённым моделям
alembic check                              # модели разошлись с миграциями?
```

Локально эти команды идут через `poetry run`, в контейнере — как есть
(`docker compose run --rm bot alembic upgrade head`).

Словарь в поставку не входит: миграции создают пустые таблицы, а чем их
наполнить — решает владелец бота. Данные живут в трёх таблицах: `categories`
(`slug`, `title`), `words` (`category_id`, `text`, `difficulty` от 1 до 3) и
`spy_hints` (`word_id`, `hint_text`). Бот берёт случайное слово среди активных
(`is_active`) и выдаёт шпиону одну из его подсказок, так что у слова должна
быть хотя бы одна.

`title` категории ведущий видит на кнопке при сборе состава, так что писать
его стоит по-человечески: «Еда», а не `food`. Выбор категорий бот предлагает
только тогда, когда их хотя бы две — категории без единого активного слова в
список не попадают, а если ведущий не отметил ни одной, слово берётся из всего
словаря. Отмеченные категории запоминаются в партии, поэтому «Ещё партия»
загадывает слово из них же. Внутри выбора все категории равноправны: сначала
жребий решает категорию, потом уже слово, так что большой раздел не заглушает
маленький.

```bash
docker compose exec postgres psql -U undercover -d undercover
```

Ненужное слово или целую категорию удобнее не удалять, а выключить:
`UPDATE words SET is_active = false WHERE id = ...` — журнал партий ссылается
на слова и переживёт выключение, но не удаление.

## Разработка без Docker

Нужен [Poetry](https://python-poetry.org/docs/#installation) 2.1+ и Python 3.13
или 3.14.

```bash
poetry install                # окружение и все зависимости из poetry.lock

# PostgreSQL и Redis всё равно нужны — можно поднять только их:
docker compose up -d postgres redis
# и указать в .env: POSTGRES_HOST=localhost, REDIS_URL=redis://localhost:6379/0

poetry run alembic upgrade head
poetry run undercover-bot
```

Виртуальное окружение Poetry заводит сам и держит у себя
(`poetry env info --path`) — руками его создавать не нужно и активировать
тоже: хватает `poetry run`, а если хочется без префикса,
`eval $(poetry env activate)`. Версии зависимостей закреплены в `poetry.lock`:
`poetry add`/`poetry update` меняют его, а `poetry check --lock` ловит
рассинхрон с `pyproject.toml` — эту же проверку гоняет CI.

Логи выбирают формат по выводу: в терминале — читаемые колонки, в контейнере —
JSON для сборщика логов.

Карточки можно посмотреть, не поднимая бота: `poetry run python
tools/card_preview.py` раскладывает примеры всех экранов в `docs/preview`, а
`poetry run python tools/card_templates.py` печёт подложки из фотографий
`assets/backgrounds/` и кладёт готовые в пакет.

## Проверки

Ровно те же команды гоняет CI:

```bash
poetry check --lock               # lock не разошёлся с pyproject
poetry run ruff check .           # линт
poetry run ruff format --check .  # форматирование
poetry run mypy                   # типы, strict

poetry run pytest                      # все тесты
poetry run pytest -m "not integration" # без Docker
poetry run pytest --cov                # с покрытием
```

Интеграционные тесты поднимают одноразовые PostgreSQL и Redis через
testcontainers — без Docker они не падают, а пропускаются.
