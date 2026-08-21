#!/usr/bin/env python3
import argparse
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

BAR_WIDTH = 24


def bar(rate: float, width: int = BAR_WIDTH) -> str:
    filled = round(rate * width)
    return "█" * filled + "░" * (width - filled)


def counters(node: ET.Element) -> tuple[int, int, int, int]:
    lines_covered = lines_valid = branches_covered = branches_valid = 0
    for line in node.iter("line"):
        lines_valid += 1
        if int(line.get("hits", "0")) > 0:
            lines_covered += 1
        if (line.get("branch") or "").lower() != "true":
            continue
        coverage = line.get("condition-coverage", "")
        if "(" in coverage and "/" in coverage:
            covered, valid = coverage.split("(", 1)[1].rstrip(")").split("/")
            branches_covered += int(covered)
            branches_valid += int(valid)
    return lines_covered, lines_valid, branches_covered, branches_valid


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

    packages: dict[str, list[int]] = {}
    total = [0, 0, 0, 0]
    for file in files:
        for package in ET.parse(file).getroot().iter("package"):
            name = package.get("name") or "."
            slot = packages.setdefault(
                "undercover" if name == "." else f"undercover.{name}", [0] * 4
            )
            for index, value in enumerate(counters(package)):
                slot[index] += value
                total[index] += value

    line_rate = total[0] / total[1] if total[1] else 0.0
    branch_rate = total[2] / total[3] if total[3] else 0.0
    min_line = args.min_line / 100
    min_branch = args.min_branch / 100
    ok = line_rate >= min_line and branch_rate >= min_branch

    rows = [
        f"## {args.title}: {'passed' if ok else 'failed'}",
        "",
        f"`{bar(line_rate)}` **{line_rate * 100:.1f}%** lines "
        f"({total[0]}/{total[1]}), floor {args.min_line:.0f}%",
        "",
        f"`{bar(branch_rate)}` **{branch_rate * 100:.1f}%** branches "
        f"({total[2]}/{total[3]}), floor {args.min_branch:.0f}%",
        "",
        "| Result | Package | Lines | Branches |",
        "|---|---|---:|---:|",
    ]
    for name, (lines_covered, lines_valid, branches_covered, branches_valid) in sorted(
        packages.items(), key=lambda item: item[1][0] / max(item[1][1], 1)
    ):
        rate = lines_covered / lines_valid if lines_valid else 0.0
        branches = (
            f"{branches_covered / branches_valid * 100:.1f}% "
            f"<sub>{branches_covered}/{branches_valid}</sub>"
            if branches_valid
            else "—"
        )
        rows.append(
            f"| {'ok' if rate >= min_line else 'low'} | `{name}` | "
            f"{rate * 100:.1f}% <sub>{lines_covered}/{lines_valid}</sub> | {branches} |"
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
