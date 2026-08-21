import importlib

import pytest

PACKAGES = [
    "undercover",
    "undercover.log",
    "undercover.bot",
    "undercover.bot.middlewares",
    "undercover.bot.routers",
    "undercover.db",
    "undercover.db.repositories",
    "undercover.game",
    "undercover.media",
    "undercover.redis",
    "undercover.utils",
]


@pytest.mark.parametrize("name", PACKAGES)
def test_package_is_importable(name: str) -> None:
    importlib.import_module(name)


def test_entrypoint_exposes_main() -> None:
    main_module = importlib.import_module("undercover.main")
    assert callable(main_module.main)
