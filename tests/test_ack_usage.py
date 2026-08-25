import ast
from pathlib import Path

SOURCES = Path("src/undercover/bot")

ALLOWED = {SOURCES / "acks.py"}


def answers_directly(source: Path) -> bool:
    tree = ast.parse(source.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "answer"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in {"callback", "event"}
        ):
            return True
    return False


def test_callbacks_are_answered_through_the_ack_wrapper() -> None:
    offenders = sorted(
        str(source)
        for source in SOURCES.rglob("*.py")
        if source not in ALLOWED and answers_directly(source)
    )

    assert offenders == []
