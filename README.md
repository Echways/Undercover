# Undercover

[![CI](https://github.com/Echways/undercover-game-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/Echways/undercover-game-bot/actions/workflows/ci.yml)

Telegram-бот для игры в шпиона с одного телефона.

Все игроки, кроме шпионов, получают одно и то же слово; шпиону достаётся только
подсказка. Телефон передаётся по кругу, каждый смотрит свою карточку, затем все
по очереди называют по одной ассоциации — и ищут того, кто выкручивается.

Ведущий собирает состав в диалоге с ботом, а дальше вся партия живёт в одном
сообщении: карточка сменяет карточку, чат не засоряется.

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
docker compose run --rm bot undercover-seed       # словарь игры
```

Порядок важен: без миграций боту некуда писать журнал партий, без сидера —
нечего загадывать, и первая же партия упрётся в «словарь игры не готов».

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
compose.yaml        бот, PostgreSQL и Redis для локального запуска
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
undercover-seed                            # налить словарь (идемпотентно)
```

Сидер можно запускать сколько угодно раз: он добавляет только недостающие слова
и подсказки и не трогает то, что оператор выключил вручную.

## Разработка без Docker

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# PostgreSQL и Redis всё равно нужны — можно поднять только их:
docker compose up -d postgres redis
# и указать в .env: POSTGRES_HOST=localhost, REDIS_URL=redis://localhost:6379/0

alembic upgrade head
undercover-seed
undercover-bot
```

Логи выбирают формат по выводу: в терминале — читаемые колонки, в контейнере —
JSON для сборщика логов.

Карточки можно посмотреть, не поднимая бота: `python tools/card_preview.py`
раскладывает примеры всех экранов в `docs/preview`, а `python
tools/card_templates.py` пересобирает фоны, которые лежат в пакете.

## Проверки

Ровно те же команды гоняет CI:

```bash
ruff check .           # линт
ruff format --check .  # форматирование
mypy                   # типы, strict

pytest                      # все тесты
pytest -m "not integration" # без Docker
pytest --cov                # с покрытием
```

Интеграционные тесты поднимают одноразовые PostgreSQL и Redis через
testcontainers — без Docker они не падают, а пропускаются.
