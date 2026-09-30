"""Process-local cancellation registry for owner-scoped Run cancellation."""

from __future__ import annotations

from threading import Lock

from app.harness.budget import CancellationToken


class CancellationStore:
    """Map active Run ids to trusted in-process cancellation tokens."""

    def __init__(self) -> None:
        self._tokens: dict[str, CancellationToken] = {}
        self._lock = Lock()

    def register(self, run_id: str, token: CancellationToken) -> None:
        normalized = str(run_id).strip()
        if not normalized:
            raise ValueError("run_id is required")
        with self._lock:
            self._tokens[normalized] = token

    def cancel(self, run_id: str) -> bool:
        normalized = str(run_id).strip()
        with self._lock:
            token = self._tokens.get(normalized)
        if token is None:
            return False
        token.cancel()
        return True

    def unregister(self, run_id: str, token: CancellationToken | None = None) -> None:
        normalized = str(run_id).strip()
        with self._lock:
            current = self._tokens.get(normalized)
            if current is not None and (token is None or current is token):
                self._tokens.pop(normalized, None)


cancellation_store = CancellationStore()
