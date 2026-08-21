import pytest

from conftest import SetEnv
from undercover.config import ConfigurationError, load_settings


def test_loads_valid_environment(set_env: SetEnv) -> None:
    set_env()
    settings = load_settings()

    assert settings.bot_token.get_secret_value() == "123456789:AA-test-token"
    assert settings.postgres_port == 5432
    assert settings.log_level == "INFO"
    assert (
        settings.postgres_dsn == "postgresql+asyncpg://undercover:s3cret@postgres:5432/undercover"
    )


def test_postgres_dsn_escapes_credentials(set_env: SetEnv) -> None:
    set_env(POSTGRES_USER="sp@bot", POSTGRES_PASSWORD="p@ss:w/ord?")
    assert load_settings().postgres_dsn == (
        "postgresql+asyncpg://sp%40bot:p%40ss%3Aw%2Ford%3F@postgres:5432/undercover"
    )


@pytest.mark.parametrize("level", ["debug", "Warning", "ERROR"])
def test_log_level_is_case_insensitive(set_env: SetEnv, level: str) -> None:
    set_env(LOG_LEVEL=level)
    assert load_settings().log_level == level.upper()


def test_targets_carry_no_credentials(set_env: SetEnv) -> None:
    set_env(REDIS_URL="redis://:redis-password@redis:6380/2")
    settings = load_settings()

    assert settings.postgres_target == "postgres:5432/undercover"
    assert settings.redis_target == "redis:6380/2"
    assert "s3cret" not in settings.postgres_target
    assert "redis-password" not in settings.redis_target


@pytest.mark.parametrize(
    ("overrides", "expected_field"),
    [
        ({"BOT_TOKEN": None}, "bot_token"),
        ({"BOT_TOKEN": ""}, "bot_token"),
        ({"POSTGRES_PORT": "not-a-number"}, "postgres_port"),
        ({"POSTGRES_PORT": "0"}, "postgres_port"),
        ({"POSTGRES_PORT": "70000"}, "postgres_port"),
        ({"POSTGRES_DB": ""}, "postgres_db"),
        ({"POSTGRES_PASSWORD": ""}, "postgres_password"),
        ({"REDIS_URL": "not-a-url"}, "redis_url"),
        ({"REDIS_URL": None}, "redis_url"),
        ({"LOG_LEVEL": "LOUD"}, "log_level"),
    ],
)
def test_invalid_environment_is_reported_readably(
    set_env: SetEnv, overrides: dict[str, str | None], expected_field: str
) -> None:
    set_env(**overrides)

    with pytest.raises(ConfigurationError) as error:
        load_settings()

    message = str(error.value)
    assert "неверная конфигурация окружения" in message
    assert expected_field in message


def test_validation_message_does_not_leak_secrets(set_env: SetEnv) -> None:
    set_env(POSTGRES_PORT="not-a-number")

    with pytest.raises(ConfigurationError) as error:
        load_settings()

    assert "s3cret" not in str(error.value)
    assert "123456789:AA-test-token" not in str(error.value)
