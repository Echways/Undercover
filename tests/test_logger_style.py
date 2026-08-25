import ast
from pathlib import Path

SOURCES = Path("src/undercover")

ALLOWED = {
    SOURCES / "log.py",
    SOURCES / "main.py",
}


def uses_stdlib_logger(source: Path) -> bool:
    tree = ast.parse(source.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "getLogger":
            return True
    return False


def test_only_the_logging_setup_touches_stdlib_logging() -> None:
    offenders = sorted(
        str(source)
        for source in SOURCES.rglob("*.py")
        if source not in ALLOWED and uses_stdlib_logger(source)
    )

    assert offenders == []
