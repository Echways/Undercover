import ast
from pathlib import Path

ROUTERS = Path("src/undercover/bot/routers")

PACKAGE = "undercover.bot.routers"


def as_unit(name: str) -> str:
    """Роутер по имени модуля или пакета: `lobby.py` — «lobby», `setup/` — «setup»."""
    return name.removesuffix(".py").split("_")[0]


def unit_of(source: Path) -> str:
    return as_unit(source.relative_to(ROUTERS).parts[0])


def imported_units(source: Path) -> set[str]:
    tree = ast.parse(source.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            if node.module == PACKAGE or not node.module.startswith(f"{PACKAGE}."):
                continue
            found.add(as_unit(node.module[len(PACKAGE) + 1 :].split(".")[0]))
    return found


def test_no_router_imports_another_router() -> None:
    offenders = {
        str(source.relative_to(ROUTERS)): sorted(strangers)
        for source in sorted(ROUTERS.rglob("*.py"))
        if (strangers := imported_units(source) - {unit_of(source)})
    }

    assert offenders == {}, f"роутеры импортируют друг друга: {offenders}"
