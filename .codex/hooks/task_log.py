#!/usr/bin/env python3
"""Repository-local Codex task logger.

Reads one Codex hook event JSON object from stdin.
Commands:
  start      UserPromptSubmit
  tool       PostToolUse (Bash)
  stop       Stop
  interrupt  Interrupt

No third-party dependencies.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable


MAX_PROMPT = 12000
MAX_RESULT = 12000
MAX_COMMAND = 2000

VALIDATION_RE = re.compile(
    r"(?ix)"
    r"(?:^|\s|[;&|])("
    r"pytest|python\s+-m\s+pytest|uv\s+run\s+pytest|"
    r"ruff(?:\s+check|\s+format)?|mypy|pyright|"
    r"tox|nox|"
    r"npm\s+(?:run\s+)?(?:test|lint|check|build)|"
    r"pnpm\s+"
    r"(?:(?:--dir|-C)(?:=|\s+)(?:\"[^\"]+\"|'[^']+'|[^\s;&|]+)\s+)?"
    r"(?:run\s+)?(?:test|lint|check|typecheck|build)(?![\w-])|"
    r"yarn\s+(?:run\s+)?(?:test|lint|check|build)|"
    r"bun\s+(?:run\s+)?(?:test|lint|check|build)|"
    r"vitest|jest|"
    r"cargo\s+(?:test|check|clippy|build)|"
    r"go\s+test|"
    r"dotnet\s+(?:test|build)|"
    r"gradle(?:w)?\s+(?:test|check|build)|"
    r"mvn(?:w)?\s+(?:test|verify|package)|"
    r"make\s+(?:test|check|lint|build)"
    r")\b"
)

def redact_assignment(match: re.Match[str]) -> str:
    value = match.group(3)
    quote = value[0] if value[0] in "\"'" else ""
    return f"{match.group(1)}{match.group(2)}{quote}[REDACTED]{quote}"


SECRET_PATTERNS = [
    (re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._~+/=-]{12,}"), r"\1 [REDACTED]"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"), "[REDACTED_API_KEY]"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"), "[REDACTED_GITHUB_TOKEN]"),
    (
        re.compile(
            r"(?i)\b(api[_-]?key|token|password|passwd|secret)\b"
            r"([\"']?\s*[:=]\s*)"
            r"(\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|[^\s,'\";]+)"
        ),
        redact_assignment,
    ),
]


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso(ts: dt.datetime | None = None) -> str:
    return (ts or now_utc()).isoformat(timespec="seconds")


def redact(value: Any) -> str:
    text = "" if value is None else str(value)
    for pattern, repl in SECRET_PATTERNS:
        text = pattern.sub(repl, text)
    return text


def clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n\n[truncated by ai-task-log]"


def run_git(cwd: Path, *args: str) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            ["git", "-C", str(cwd), *args],
            text=True,
            capture_output=True,
            check=False,
        )
        return proc.returncode, proc.stdout.rstrip("\r\n")
    except OSError:
        return 127, ""


def git_root(cwd: Path) -> Path | None:
    code, out = run_git(cwd, "rev-parse", "--show-toplevel")
    if code != 0 or not out:
        return None
    return Path(out).resolve()


def current_branch(root: Path) -> str:
    code, out = run_git(root, "branch", "--show-current")
    return out if code == 0 and out else "(detached)"


def current_commit(root: Path) -> str:
    code, out = run_git(root, "rev-parse", "HEAD")
    return out if code == 0 else "(unknown)"


def event_from_stdin() -> dict[str, Any]:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def state_paths(root: Path, turn_id: str) -> tuple[Path, Path]:
    state = root / ".ai" / "state"
    state.mkdir(parents=True, exist_ok=True)
    safe_turn = re.sub(r"[^A-Za-z0-9_.-]", "_", turn_id or "unknown")
    return state / f"{safe_turn}.json", state / f"{safe_turn}.tools.jsonl"


def atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def infer_root(event: dict[str, Any]) -> Path | None:
    cwd_raw = event.get("cwd") or os.getcwd()
    cwd = Path(str(cwd_raw)).expanduser()
    try:
        cwd = cwd.resolve()
    except OSError:
        pass
    return git_root(cwd)


def start(event: dict[str, Any]) -> int:
    root = infer_root(event)
    if root is None:
        return 0
    turn_id = str(event.get("turn_id") or "unknown")
    state_path, tools_path = state_paths(root, turn_id)
    state = {
        "schema_version": 1,
        "started_at": iso(),
        "session_id": event.get("session_id"),
        "turn_id": turn_id,
        "model": event.get("model"),
        "permission_mode": event.get("permission_mode"),
        "cwd": event.get("cwd"),
        "prompt": clip(redact(event.get("prompt")), MAX_PROMPT),
        "branch": current_branch(root),
        "base_commit": current_commit(root),
    }
    atomic_write_json(state_path, state)
    if not tools_path.exists():
        tools_path.touch()
    return 0


def tool(event: dict[str, Any]) -> int:
    if str(event.get("tool_name") or "") != "Bash":
        return 0
    root = infer_root(event)
    if root is None:
        return 0
    turn_id = str(event.get("turn_id") or "unknown")
    _, tools_path = state_paths(root, turn_id)
    tool_input = event.get("tool_input")
    command = ""
    if isinstance(tool_input, dict):
        command = str(tool_input.get("command") or "")
    record = {
        "at": iso(),
        "tool_use_id": event.get("tool_use_id"),
        "command": clip(redact(command), MAX_COMMAND),
        "exit_code": extract_exit_code(event.get("tool_response")),
    }
    with tools_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return 0


def walk(obj: Any) -> Iterable[tuple[str | None, Any]]:
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield str(k), v
            yield from walk(v)
    elif isinstance(obj, list):
        for item in obj:
            yield None, item
            yield from walk(item)


def extract_exit_code(response: Any) -> int | None:
    preferred = {
        "exit_code",
        "exitcode",
        "exitCode",
        "returncode",
        "return_code",
        "status_code",
    }
    for key, value in walk(response):
        if key in preferred:
            try:
                return int(value)
            except (TypeError, ValueError):
                pass

    text = redact(response)
    patterns = [
        r"(?i)\bprocess exited with code\s+(-?\d+)\b",
        r"(?i)\bexit(?:ed)?\s+code[:=]?\s*(-?\d+)\b",
        r"(?i)\breturn\s+code[:=]?\s*(-?\d+)\b",
    ]
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                pass
    return None


def read_tools(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            obj = json.loads(line)
            if isinstance(obj, dict):
                rows.append(obj)
        except json.JSONDecodeError:
            continue
    return rows


def unique_changed_files(root: Path, base_commit: str, end_commit: str) -> list[str]:
    names: list[str] = []

    def add_output(args: list[str]) -> None:
        code, out = run_git(root, *args)
        if code == 0 and out:
            names.extend(x.strip() for x in out.splitlines() if x.strip())

    if (
        base_commit
        and end_commit
        and base_commit != "(unknown)"
        and end_commit != "(unknown)"
        and base_commit != end_commit
    ):
        add_output(["diff", "--name-only", f"{base_commit}..{end_commit}"])

    add_output(["diff", "--name-only"])
    add_output(["diff", "--cached", "--name-only"])

    code, status = run_git(root, "status", "--porcelain")
    if code == 0:
        for line in status.splitlines():
            if len(line) >= 4:
                path = line[3:].strip()
                if " -> " in path:
                    path = path.split(" -> ", 1)[1]
                if path:
                    names.append(path)

    seen: set[str] = set()
    result: list[str] = []
    for name in names:
        if name not in seen:
            seen.add(name)
            result.append(name)
    return result


def validation_rows(tools: list[dict[str, Any]]) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for rec in tools:
        command = str(rec.get("command") or "").strip()
        if not command or not VALIDATION_RE.search(command):
            continue
        exit_code = rec.get("exit_code")
        if exit_code == 0:
            status = "PASS"
        elif isinstance(exit_code, int):
            status = f"FAIL (exit {exit_code})"
        else:
            status = "UNKNOWN"
        rows.append((status, command))
    return rows


def markdown_code(text: str) -> str:
    # Four-backtick fence survives ordinary triple-backtick content in assistant output.
    return f"````text\n{text.rstrip()}\n````"


def finalize(event: dict[str, Any], status: str) -> int:
    root = infer_root(event)
    if root is None:
        return 0

    turn_id = str(event.get("turn_id") or "unknown")
    state_path, tools_path = state_paths(root, turn_id)
    state: dict[str, Any] = {}
    if state_path.exists():
        try:
            loaded = json.loads(state_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                state = loaded
        except json.JSONDecodeError:
            pass

    started_at_raw = str(state.get("started_at") or iso())
    try:
        started_at = dt.datetime.fromisoformat(started_at_raw)
    except ValueError:
        started_at = now_utc()

    end_commit = current_commit(root)
    branch = current_branch(root)
    base_commit = str(state.get("base_commit") or "(unknown)")
    files = unique_changed_files(root, base_commit, end_commit)
    tools = read_tools(tools_path)
    validations = validation_rows(tools)

    code, repo_status = run_git(root, "status", "--short")
    if code != 0:
        repo_status = "(git status unavailable)"

    result = event.get("last_assistant_message")
    if status == "Interrupted" and not result:
        result = "Turn interrupted before a final assistant message was available."
    result_text = clip(redact(result or "(no final assistant message)"), MAX_RESULT)
    prompt_text = str(state.get("prompt") or "(prompt not captured)")

    short_turn = re.sub(r"[^A-Za-z0-9]", "", turn_id)[-8:] or "unknown"
    month_dir = root / ".ai" / "runs" / started_at.strftime("%Y-%m")
    month_dir.mkdir(parents=True, exist_ok=True)
    stem = started_at.strftime("%Y%m%d-%H%M%S")
    out_path = month_dir / f"{stem}-{short_turn}.md"
    if out_path.exists():
        suffix = 2
        while (month_dir / f"{stem}-{short_turn}-{suffix}.md").exists():
            suffix += 1
        out_path = month_dir / f"{stem}-{short_turn}-{suffix}.md"

    lines: list[str] = [
        f"# AI Run — {started_at.isoformat(timespec='seconds')}",
        "",
        "## Metadata",
        "",
        f"- Status: {status}",
        "- Agent: Codex",
        f"- Model: {redact(state.get('model') or event.get('model') or '(unknown)')}",
        f"- Session: {redact(state.get('session_id') or event.get('session_id') or '(unknown)')}",
        f"- Turn: {redact(turn_id)}",
        f"- Branch: {redact(branch)}",
        f"- Base commit: {redact(base_commit)}",
        f"- End commit: {redact(end_commit)}",
        f"- Started: {redact(started_at_raw)}",
        f"- Finished: {iso()}",
        "",
        "## Task",
        "",
        markdown_code(prompt_text),
        "",
        "## Result",
        "",
        result_text,
        "",
        "## Files Changed",
        "",
    ]

    if files:
        lines.extend(f"- `{redact(name)}`" for name in files)
    else:
        lines.append("- None detected by Git.")

    lines.extend(["", "## Validation Observed", ""])
    if validations:
        for observed_status, command in validations:
            lines.append(f"- **{observed_status}** — `{redact(command)}`")
    else:
        lines.append("- No recognized validation command was observed by the Bash PostToolUse hook.")

    lines.extend(["", "## Repository Status", ""])
    if repo_status:
        lines.append(markdown_code(redact(repo_status)))
    else:
        lines.append("Clean working tree.")

    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- Validation status is based only on commands actually observed by the hook.",
            "- `UNKNOWN` means the hook could not reliably extract an exit code.",
            "- Full tool output, diffs, file contents, transcripts, and chain-of-thought are not stored.",
            "",
        ]
    )

    out_path.write_text("\n".join(lines), encoding="utf-8")

    for path in (state_path, tools_path):
        try:
            path.unlink()
        except FileNotFoundError:
            pass
    return 0


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in {"start", "tool", "stop", "interrupt"}:
        return 0
    event = event_from_stdin()
    action = sys.argv[1]
    if action == "start":
        return start(event)
    if action == "tool":
        return tool(event)
    if action == "stop":
        return finalize(event, "Completed")
    return finalize(event, "Interrupted")


if __name__ == "__main__":
    raise SystemExit(main())
