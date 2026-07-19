"""Thread identifiers and ownership boundaries for Agent runs.

The client-facing id is deliberately kept separate from the checkpointer key.
Checkpoint and memory stores must never use a caller-controlled id without a
server-owned namespace.
"""

from dataclasses import dataclass
import re
from uuid import uuid4


_THREAD_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._~-]{0,127}$")


@dataclass(frozen=True)
class UserThread:
    user_id: int
    public_id: str
    internal_id: str


@dataclass(frozen=True)
class AnonymousThread:
    public_id: None
    internal_id: str


def _validate_public_id(thread_id: str) -> str:
    if not isinstance(thread_id, str) or not _THREAD_ID_RE.fullmatch(thread_id):
        raise ValueError(
            "thread_id must be 1-128 characters and contain only letters, "
            "numbers, '.', '_', '~' or '-'."
        )
    return thread_id


def make_user_thread(user_id: int, thread_id: str) -> UserThread:
    if not isinstance(user_id, int) or user_id <= 0:
        raise ValueError("user_id must be a positive integer")
    public_id = _validate_public_id(thread_id)
    return UserThread(
        user_id=user_id,
        public_id=public_id,
        internal_id=f"user:{user_id}:thread:{public_id}",
    )


def make_anonymous_thread() -> AnonymousThread:
    return AnonymousThread(public_id=None, internal_id=f"anon:{uuid4().hex}")


def public_thread_id(user_id: int, internal_id: str) -> str | None:
    prefix = f"user:{user_id}:thread:"
    if not isinstance(internal_id, str) or not internal_id.startswith(prefix):
        return None
    candidate = internal_id[len(prefix):]
    try:
        return _validate_public_id(candidate)
    except ValueError:
        return None


def user_thread_prefix(user_id: int) -> str:
    if not isinstance(user_id, int) or user_id <= 0:
        raise ValueError("user_id must be a positive integer")
    return f"user:{user_id}:thread:"
