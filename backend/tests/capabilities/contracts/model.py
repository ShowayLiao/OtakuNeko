"""Explicit action examples; dependencies are isolated, implementations are real."""

from dataclasses import dataclass, field
from collections.abc import Awaitable, Callable
from typing import Any


@dataclass
class Environment:
    monkeypatch: Any
    db: Any
    user: Any
    calls: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Case:
    arguments: dict[str, Any]
    expected: dict[str, Any]
    prepare: Callable[[Environment], Awaitable[None]]
