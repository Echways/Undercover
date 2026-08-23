#!/usr/bin/env python3
import argparse
import os
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

BAR_WIDTH = 24


def bar(rate: float, width: int = BAR_WIDTH) -> str:
    filled = round(rate * width)
    return "█" * filled + "░" * (width - filled)


@dataclass
class Tally:
    lines_covered: int = 0
    lines_valid: int = 0
    branches_covered: int = 0
    branches_valid: int = 0

    @property
    def line_rate(self) -> float:
        return self.lines_covered / self.lines_valid if self.lines_valid else 0.0

    @property
    def branch_rate(self) -> float:
        return self.branches_covered / self.branches_valid if self.branches_valid else 0.0

    def add(self, other: "Tally") -> None:
        self.lines_covered += other.lines_covered
        self.lines_valid += other.lines_valid
        self.branches_covered += other.branches_covered
        self.branches_valid += other.branches_valid


def counters(node: ET.Element) -> Tally:
    tally = Tally()
    for line in node.iter("line"):
        tally.lines_valid += 1
        if int(line.get("hits", "0")) > 0:
            tally.lines_covered += 1
        if (line.get("branch") or "").lower() != "true":
            continue
        coverage = line.get("condition-coverage", "")
        if "(" in coverage and "/" in coverage:
            covered, valid = coverage.split("(", 1)[1].rstrip(")").split("/")
            tally.branches_covered += int(covered)
            tally.branches_valid += int(valid)
    return tally


def gather(paths: list[str]) -> list[Path]:
    files: list[Path] = []
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            files.extend(sorted(path.rglob("coverage*.xml")))
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
    parser.add_argument("paths", nargs="+", help="coverage xml files or directories to scan")
    parser.add_argument("--min-line", type=float, default=0.0)
    parser.add_argument("--min-branch", type=float, default=0.0)
    parser.add_argument("--title", default="Coverage")
    args = parser.parse_args()

    files = gather(args.paths)
    if not files:
        emit(f"## {args.title}: no data\n\n> No coverage report was produced.\n")
        return 1

    packages: dict[str, Tally] = {}
    total = Tally()
    for file in files:
        for package in ET.parse(file).getroot().iter("package"):
            name = package.get("name") or "."
            counted = counters(package)
            packages.setdefault("undercover" if name == "." else f"undercover.{name}", Tally()).add(
                counted
            )
            total.add(counted)

    line_rate = total.line_rate
    branch_rate = total.branch_rate
    min_line = args.min_line / 100
    min_branch = args.min_branch / 100
    ok = line_rate >= min_line and branch_rate >= min_branch

    rows = [
        f"## {args.title}: {'passed' if ok else 'failed'}",
        "",
        f"`{bar(line_rate)}` **{line_rate * 100:.1f}%** lines "
        f"({total.lines_covered}/{total.lines_valid}), floor {args.min_line:.0f}%",
        "",
        f"`{bar(branch_rate)}` **{branch_rate * 100:.1f}%** branches "
        f"({total.branches_covered}/{total.branches_valid}), floor {args.min_branch:.0f}%",
        "",
        "| Result | Package | Lines | Branches |",
        "|---|---|---:|---:|",
    ]
    for name, tally in sorted(packages.items(), key=lambda item: item[1].line_rate):
        branches = (
            f"{tally.branch_rate * 100:.1f}% "
            f"<sub>{tally.branches_covered}/{tally.branches_valid}</sub>"
            if tally.branches_valid
            else "—"
        )
        rows.append(
            f"| {'ok' if tally.line_rate >= min_line else 'low'} | `{name}` | "
            f"{tally.line_rate * 100:.1f}% "
            f"<sub>{tally.lines_covered}/{tally.lines_valid}</sub> | {branches} |"
        )
    rows.append("")

    if not ok:
        rows += [
            f"> Below the floor: lines {line_rate * 100:.1f}%, branches {branch_rate * 100:.1f}%.",
            "",
        ]

    emit("\n".join(rows))

    if path := os.environ.get("GITHUB_OUTPUT"):
        with Path(path).open("a", encoding="utf-8") as handle:
            handle.write(f"line-rate={line_rate * 100:.1f}\nbranch-rate={branch_rate * 100:.1f}\n")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
