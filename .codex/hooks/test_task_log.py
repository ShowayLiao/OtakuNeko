"""Regression tests for validation commands captured by the task logger."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import task_log
from task_log import redact, validation_rows


class ValidationRowsTests(unittest.TestCase):
    def test_repository_frontend_commands_are_recorded(self):
        for script in ("lint", "typecheck", "test", "build"):
            command = f"pnpm --dir frontend {script}"
            with self.subTest(command=command):
                self.assertEqual(
                    validation_rows([{"command": command, "exit_code": 0}]),
                    [("PASS", command)],
                )

    def test_directory_options_and_run_preserve_exit_status(self):
        for directory in (
            "--dir frontend",
            "--dir=frontend",
            "-C frontend",
            '--dir "frontend project"',
            "--dir 'frontend project'",
        ):
            command = f"pnpm {directory} run typecheck"
            for exit_code, expected in ((0, "PASS"), (1, "FAIL (exit 1)"), (None, "UNKNOWN")):
                with self.subTest(command=command, exit_code=exit_code):
                    self.assertEqual(
                        validation_rows([{"command": command, "exit_code": exit_code}]),
                        [(expected, command)],
                    )

    def test_existing_validation_commands_remain_recognized(self):
        for command in (
            "pnpm test",
            "pnpm run lint",
            "pnpm typecheck",
            "uv run --directory backend pytest",
            "uv run --directory backend ruff check app tests",
            "npm run build",
        ):
            with self.subTest(command=command):
                self.assertEqual(
                    validation_rows([{"command": command, "exit_code": 0}]),
                    [("PASS", command)],
                )

    def test_non_validation_commands_are_not_recorded(self):
        for command in (
            "pnpm --dir frontend dev",
            "pnpm --dir frontend install",
            "pnpm --dir frontend run typechecker",
            "pnpm --dir frontend build-assets",
        ):
            with self.subTest(command=command):
                self.assertEqual(validation_rows([{"command": command, "exit_code": 0}]), [])


class RedactionTests(unittest.TestCase):
    def test_quoted_credentials_are_redacted(self):
        for text in (
            'api_key="example-secret-12345"',
            "API_KEY='example-secret-12345'",
            '{"password": "example-secret-12345"}',
            "{'token': 'example-secret-12345'}",
            '{"secret": "example-secret-12345 with spaces"}',
            r'{"password": "example-secret-12345\"tail"}',
            '{"apiKey": "example-secret-12345", "model": "safe-model"}',
            'password=example-secret-12345',
            '{"password": example-secret-12345}',
        ):
            with self.subTest(text=text):
                safe_text = redact(text)
                self.assertNotIn("example-secret-12345", safe_text)
                self.assertNotIn("tail", safe_text)
                self.assertIn("[REDACTED]", safe_text)

    def test_redaction_preserves_json_and_safe_fields(self):
        text = '{"password": "example-password-12345", "model": "safe-model"}'
        self.assertEqual(
            json.loads(redact(text)),
            {"password": "[REDACTED]", "model": "safe-model"},
        )

    def test_lifecycle_never_persists_quoted_credentials(self):
        # Exercise the actual logger lifecycle in an isolated temporary root.
        # No real repository task logs or credentials are read or written.
        with tempfile.TemporaryDirectory() as temporary_root:
            root = Path(temporary_root)
            event = {"turn_id": "synthetic-turn", "session_id": "synthetic-session"}
            with (
                patch.object(task_log, "infer_root", return_value=root),
                patch.object(task_log, "current_branch", return_value="test-branch"),
                patch.object(task_log, "current_commit", return_value="test-commit"),
                patch.object(task_log, "unique_changed_files", return_value=[]),
                patch.object(task_log, "run_git", return_value=(0, "")),
            ):
                task_log.start({**event, "prompt": '{"password": "example-prompt-secret"}'})
                state_file = root / ".ai/state/synthetic-turn.json"
                self.assertNotIn("example-prompt-secret", state_file.read_text(encoding="utf-8"))

                task_log.tool({
                    **event,
                    "tool_name": "Bash",
                    "tool_input": {"command": 'pnpm --dir frontend test; api_key="example-command-secret"'},
                    "tool_response": {"exit_code": 0},
                })
                tools_file = root / ".ai/state/synthetic-turn.tools.jsonl"
                self.assertNotIn("example-command-secret", tools_file.read_text(encoding="utf-8"))

                task_log.finalize({
                    **event,
                    "last_assistant_message": '{"token": "example-result-secret"}',
                }, "Completed")
                reports = list((root / ".ai/runs").glob("*/*.md"))
                self.assertEqual(len(reports), 1)
                report = reports[0].read_text(encoding="utf-8")
                for credential in ("example-prompt-secret", "example-command-secret", "example-result-secret"):
                    self.assertNotIn(credential, report)
                self.assertIn("**PASS**", report)
                self.assertIn("[REDACTED]", report)


if __name__ == "__main__":
    unittest.main()
