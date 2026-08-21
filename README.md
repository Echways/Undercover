# Undercover

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

docker compose run --rm bot alembic upgrade head       # схема базы
docker compose run --rm bot python scripts/seed_words.py  # словарь игры
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

## База данных и словарь

Схема живёт в моделях SQLAlchemy (`src/undercover/db/models.py`) и
версионируется Alembic. Отдельного DSN в `alembic.ini` нет — адрес базы берётся
из тех же переменных окружения, что и у бота.

```bash
alembic upgrade head                       # накатить схему
alembic downgrade base                     # откатить всё
alembic revision --autogenerate -m "..."   # новая миграция по изменённым моделям
alembic check                              # модели разошлись с миграциями?
python scripts/seed_words.py               # налить словарь (идемпотентно)
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
python scripts/seed_words.py
python -m undercover.main
```

Логи выбирают формат по выводу: в терминале — читаемые колонки, в контейнере —
JSON для сборщика логов.

## Тесты

```bash
pytest                      # всё
pytest -m "not integration" # без Docker
```