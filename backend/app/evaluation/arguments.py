"""Value comparison for isolated synthetic evaluation inputs only."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def argument_digest(arguments: dict[str, Any]) -> str:
    """Hash canonical JSON without retaining values in evaluation artifacts.

    Only the synthetic entrypoint capability uses this observer. This is a
    comparison digest, not a privacy mechanism for real user data or secrets.
    """
    encoded = json.dumps(
        arguments,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
