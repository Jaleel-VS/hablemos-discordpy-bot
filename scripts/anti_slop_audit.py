#!/usr/bin/env python3
"""Run anti-slop-py against first-party Python and enforce its baseline."""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

BASELINE = 0
TARGETS = (
    "cogs",
    "db",
    "tests",
    "scripts",
    "logforwarder",
)
CODE_PATTERN = re.compile(r"\b(?:ASP|ASD|ASF)\d{3}\b")


def scan() -> tuple[int, Counter[str], str]:
    """Run the first-party scan and return count, rule totals, and output."""
    command = [
        sys.executable,
        "-m",
        "flake8",
        "--select",
        "ASP",
        "--extend-ignore",
        "ASP002,ASP003",
        *TARGETS,
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    output = result.stdout + result.stderr
    rules = Counter(CODE_PATTERN.findall(output))
    return sum(rules.values()), rules, output


def main() -> int:
    """Print a compact baseline report and fail only on regressions or strict mode."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="fail if any anti-slop findings remain",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="print every finding after the summary",
    )
    args = parser.parse_args()

    count, rules, output = scan()
    breakdown = ", ".join(
        f"{code}={total}" for code, total in sorted(rules.items())
    ) or "none"
    print(f"anti-slop: {count} findings (baseline {BASELINE}); {breakdown}")
    if args.show and output:
        print(output, end="" if output.endswith("\n") else "\n")

    if args.strict and count:
        print("anti-slop: strict mode failed", file=sys.stderr)
        return 1
    if count > BASELINE:
        print(
            f"anti-slop: regression ({count - BASELINE} above baseline)",
            file=sys.stderr,
        )
        return 1
    if count < BASELINE:
        print(
            f"anti-slop: improved by {BASELINE - count}; lower BASELINE in {Path(__file__).as_posix()}",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
