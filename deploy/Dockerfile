FROM python:3.13-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src ./src

RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install .

FROM python:3.13-slim

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY --from=builder /opt/venv /opt/venv

RUN useradd --create-home --uid 1000 app
USER app
WORKDIR /home/app

COPY pyproject.toml ./

CMD ["undercover-bot"]
