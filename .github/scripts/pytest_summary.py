#!/usr/bin/env python3
import argparse
import os
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

SLOWEST = 5


@dataclass
class Suite:
    name: str
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    duration: float = 0.0
    failures: list[tuple[str, str]] = field(default_factory=list)
    slowest: list[tuple[float, str]] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.passed + self.failed + self.skipped

    @property
    def status(self) -> str:
        if self.failed:
            return "FAIL"
        return "empty" if not self.total else "ok"


def parse(path: Path) -> Suite:
    suite = Suite(name=path.stem)
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as error:
        suite.failed = 1
        suite.failures.append((path.name, f"unreadable report: {error}"))
        return suite

    for case in root.iter("testcase"):
        name = f"{case.get('classname', '')}::{case.get('name', '<unknown>')}".lstrip(":")
        seconds = float(case.get("time") or 0.0)
        suite.duration += seconds
        suite.slowest.append((seconds, name))

        problem = next(
            (child for child in case if child.tag in ("failure", "error")),
            None,
        )
        if problem is not None:
            suite.failed += 1
            message = (problem.get("message") or problem.tag).strip().splitlines()
            suite.failures.append((name, message[0] if message else problem.tag))
        elif case.find("skipped") is not None:
            suite.skipped += 1
        else:
            suite.passed += 1

    suite.slowest.sort(reverse=True)
    return suite


def gather(paths: list[str]) -> list[Path]:
    files: list[Path] = []
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            files.extend(sorted(path.rglob("*.xml")))
        elif path.is_file():
            files.append(path)
    return files


def emit(report: str) -> None:
    print(report)
    if path := os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(path).open("a", encoding="utf-8") as handle:
            handle.write(report + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", help="junit xml files or directories to scan")
    parser.add_argument("--title", default="Tests")
    parser.add_argument("--fail-on-empty", action="store_true")
    args = parser.parse_args()

    suites = [parse(file) for file in gather(args.paths)]
    if not suites:
        emit(f"## {args.title}: no data\n\n> No JUnit report was produced.\n")
        return 1

    passed = sum(suite.passed for suite in suites)
    failed = sum(suite.failed for suite in suites)
    skipped = sum(suite.skipped for suite in suites)
    duration = sum(suite.duration for suite in suites)
    empty = args.fail_on_empty and not passed + failed + skipped
    ok = not failed and not empty

    rows = [
        f"## {args.title}: {'passed' if ok else 'failed'}",
        "",
        f"**{passed}** passed · **{failed}** failed · **{skipped}** skipped · {duration:.1f}s",
        "",
        "| Result | Report | Passed | Failed | Skipped | Time |",
        "|---|---|---:|---:|---:|---:|",
    ]
    rows += [
        f"| {suite.status} | `{suite.name}` | {suite.passed} | {suite.failed} | "
        f"{suite.skipped} | {suite.duration:.1f}s |"
        for suite in suites
    ]
    rows.append("")

    failures = [failure for suite in suites for failure in suite.failures]
    if failures:
        rows += ["### Failures", ""]
        rows += [f"- `{name}` — {message}" for name, message in failures]
        rows.append("")

    slowest = sorted((entry for suite in suites for entry in suite.slowest), reverse=True)[:SLOWEST]
    if slowest and ok:
        rows += ["<details><summary>Slowest tests</summary>", ""]
        rows += [f"- `{name}` — {seconds:.2f}s" for seconds, name in slowest]
        rows += ["", "</details>", ""]

    emit("\n".join(rows))

    for name, message in failures:
        print(f"::error title={args.title}::{name} — {message}")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
