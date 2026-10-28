"""Enforce full backend Mypy coverage without hiding existing type debt."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "typecheck-baseline.json"
ERROR = re.compile(
    r"^(app|tests|alembic|scripts)[\\/](.+?):\d+(?::\d+)?: error: (.+?)  \[([^]]+)\]$"
)
SUMMARY = re.compile(
    r"^Found (\d+) errors? in \d+ files? \(checked (\d+) source files?\)$"
)
SUCCESS = re.compile(r"^Success: no issues found in (\d+) source files?$")


def parse_output(output: str) -> tuple[Counter[tuple[str, str, str]], int]:
    """Return stable error identities and the number of files Mypy checked."""
    errors: Counter[tuple[str, str, str]] = Counter()
    checked_files: int | None = None
    for line in output.splitlines():
        match = ERROR.fullmatch(line)
        if match:
            area, relative_path, message, code = match.groups()
            errors[
                (f"{area}/{relative_path.replace(chr(92), '/')}", code, message)
            ] += 1
            continue
        match = SUMMARY.fullmatch(line)
        if match:
            if int(match.group(1)) != sum(errors.values()):
                raise ValueError("Mypy summary does not match parsed errors")
            checked_files = int(match.group(2))
            continue
        match = SUCCESS.fullmatch(line)
        if match:
            checked_files = int(match.group(1))
            continue
        if ": error:" in line:
            raise ValueError(f"Unrecognized Mypy error line: {line}")
    if checked_files is None:
        raise ValueError("Mypy did not report the number of checked files")
    return errors, checked_files


def compare_baseline(
    actual: Counter[tuple[str, str, str]], checked_files: int, baseline: dict
) -> list[str]:
    allowed = Counter(
        {
            (item["path"], item["code"], item["message"]): item["count"]
            for item in baseline["errors"]
        }
    )
    failures = []
    if checked_files < baseline["checked_files"]:
        failures.append(
            f"Coverage shrank: checked {checked_files} files; baseline is "
            f"{baseline['checked_files']}"
        )
    for (path, code, message), count in sorted((actual - allowed).items()):
        failures.append(f"{path} [{code}] +{count}: {message}")
    return failures


def main() -> int:
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "mypy",
            "--no-pretty",
            "app",
            "tests",
            "alembic",
            "scripts",
            "__init__.py",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode not in (0, 1):
        print(result.stdout, end="")
        print(result.stderr, end="", file=sys.stderr)
        return result.returncode
    if result.stderr.strip():
        print(result.stderr, end="", file=sys.stderr)
        return 2
    try:
        actual, checked_files = parse_output(result.stdout)
        failures = compare_baseline(actual, checked_files, baseline)
    except ValueError as exc:
        print(result.stdout, end="")
        print(f"Typecheck baseline could not be verified: {exc}", file=sys.stderr)
        return 2
    if (result.returncode == 0) != (sum(actual.values()) == 0):
        print("Mypy exit code disagrees with parsed errors", file=sys.stderr)
        return 2
    print(
        f"Mypy checked {checked_files} files: {sum(actual.values())} errors; "
        f"baseline permits {sum(item['count'] for item in baseline['errors'])}."
    )
    if failures:
        print("New type errors or coverage regression:")
        print("\n".join(failures[:30]))
        if len(failures) > 30:
            print(f"... and {len(failures) - 30} more")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
