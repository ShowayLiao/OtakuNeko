"""Production census, explicit examples, and fail-closed coverage arithmetic."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from app.capabilities.factory import build_capability_registry
from app.capabilities.registry import CapabilityRegistry
from app.capabilities.types import ActionDescriptor
from tests.capabilities.contracts.model import Case

Key = tuple[str, str]
Observation = tuple[str, str, str]
BACKEND_ROOT = Path(__file__).resolve().parents[3]
APP_ROOT = BACKEND_ROOT / "app"
EXECUTE_METHODS = frozenset({"execute", "_execute_capability"})
ACTION_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
DATABASE_RECEIVERS = frozenset(
    {"db", "session", "connection", "cursor", "engine", "conn"}
)


def _receiver_label(node: ast.AST) -> str:
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return "<expression>"


def _is_database_receiver(receiver: str) -> bool:
    return receiver.lower().lstrip("_") in DATABASE_RECEIVERS


SCENARIOS = ("schema", "success", "error", "timeout", "isolation", "serialization")
ANIME_SCENARIOS = (
    "anime_error",
    "anime_timeout",
    "anime_isolation",
    "anime_serialization",
    "anime_authorization",
    "anime_dispatcher",
)
SUBJECTS_SCENARIOS = (
    "subjects_error",
    "subjects_timeout",
    "subjects_isolation",
    "subjects_serialization",
    "subjects_authorization",
    "subjects_dispatcher",
)
RECOMMENDATION_SCENARIOS = (
    "recommendation_error",
    "recommendation_timeout",
    "recommendation_isolation",
    "recommendation_serialization",
    "recommendation_authorization",
    "recommendation_dispatcher",
)
STATS_SCENARIOS = (
    "stats_error",
    "stats_timeout",
    "stats_isolation",
    "stats_serialization",
    "stats_authorization",
    "stats_dispatcher",
)
COLLECTIONS_READ_SCENARIOS = (
    "collections_read_error",
    "collections_read_timeout",
    "collections_read_isolation",
    "collections_read_serialization",
    "collections_read_authorization",
    "collections_read_dispatcher",
)
SCHEDULE_READ_SCENARIOS = (
    "schedule_read_error",
    "schedule_read_timeout",
    "schedule_read_isolation",
    "schedule_read_serialization",
    "schedule_read_authorization",
    "schedule_read_dispatcher",
)
MEDIA_READ_SCENARIOS = (
    "media_read_error",
    "media_read_timeout",
    "media_read_isolation",
    "media_read_serialization",
    "media_read_authorization",
    "media_read_dispatcher",
)
COLLECTIONS_WRITE_SCENARIOS = (
    "collections_write_error",
    "collections_write_timeout",
    "collections_write_isolation",
    "collections_write_serialization",
    "collections_write_authorization",
    "collections_write_dispatcher",
    "collections_write_approval",
    "collections_write_idempotency",
)
SCHEDULE_WRITE_SCENARIOS = (
    "schedule_write_error",
    "schedule_write_timeout",
    "schedule_write_isolation",
    "schedule_write_serialization",
    "schedule_write_authorization",
    "schedule_write_dispatcher",
    "schedule_write_approval",
    "schedule_write_idempotency",
    "schedule_write_recovery",
)
MEDIA_WRITE_SCENARIOS = (
    "media_write_error",
    "media_write_timeout",
    "media_write_isolation",
    "media_write_serialization",
    "media_write_authorization",
    "media_write_dispatcher",
    "media_write_approval",
    "media_write_idempotency",
    "media_write_recovery",
)
SYSTEM_SCENARIOS = (
    "system_error",
    "system_timeout",
    "system_isolation",
    "system_serialization",
    "system_authorization",
    "system_dispatcher",
)


def census(registry: CapabilityRegistry | None = None) -> dict[Key, ActionDescriptor]:
    registry = registry if registry is not None else build_capability_registry()
    result = {}
    for descriptor in registry.list_actions():
        key = (descriptor.public_name or descriptor.name, descriptor.version)
        if key in result:
            raise ValueError(f"Duplicate contract key: {key}")
        definition = registry.get_public_definition(*key)
        if definition is None or definition.name != descriptor.name:
            raise ValueError(f"Unresolvable public contract: {key}")
        result[key] = descriptor
    if not result:
        raise ValueError("Registry contract census is empty")
    return result


def cases() -> dict[Key, Case]:
    from tests.capabilities.contracts.fixtures_core import CASES as core
    from tests.capabilities.contracts.fixtures_external import CASES as external

    duplicates = set(core) & set(external)
    if duplicates:
        raise ValueError(f"Duplicate contract fixtures: {sorted(duplicates)}")
    return {**core, **external}


def fingerprint(descriptor: ActionDescriptor) -> str:
    # Descriptions are editorial; all executable schema/metadata is versioned.
    contract = descriptor.to_dict()
    contract.pop("description")
    encoded = json.dumps(contract, sort_keys=True, allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def inventory(
    actions: dict[Key, ActionDescriptor], registry: CapabilityRegistry
) -> list[dict[str, Any]]:
    """Return the compact, deterministic Registry inventory for CI evidence."""
    rows = []
    for key, descriptor in sorted(actions.items()):
        owner = registry.find_action(key[0])
        rows.append(
            {
                "public_name": key[0],
                "name": descriptor.name,
                "version": key[1],
                "owner": owner[0].name if owner is not None else None,
                "side_effect": descriptor.is_side_effect,
                "requires_auth": descriptor.requires_auth,
                "approval_required": descriptor.approval_required,
                "idempotency_mode": descriptor.idempotency_mode,
                "timeout_seconds": descriptor.timeout_seconds,
                "retry_class": descriptor.retry_class,
                "risk_level": descriptor.risk_level,
                "max_payload_bytes": descriptor.max_payload_bytes,
                "fingerprint": fingerprint(descriptor),
            }
        )
    return rows


def _literal_action(
    node: ast.AST, kind: str, *, file: str, method: str, receiver: str
) -> dict[str, Any] | None:
    if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
        return None
    if not ACTION_NAME.fullmatch(node.value):
        # SQL text and other non-action literals are not capability names.
        return None
    return {
        "file": file,
        "line": node.lineno,
        "column": node.col_offset,
        "receiver": receiver,
        "method": method,
        "kind": kind,
        "action": node.value,
    }


def invocation_audit(
    source_root: Path | None = None,
    *,
    registry: CapabilityRegistry | None = None,
    display_root: Path | None = None,
) -> dict[str, Any]:
    """Find literal direct capability calls that bypass the public Registry.

    Identifier-shaped literal action names passed positionally or as ``action=``
    to ``*.execute(...)`` and ``._execute_capability(..., public_action=...)``
    are compared with the production Registry regardless of the receiver name,
    so a renamed handle cannot hide a call. ``execute`` literals must be
    internal action names and ``public_action`` literals must be public names.
    Exact database/session/connection/cursor/engine/conn receivers and SQL text
    are excluded; other expressions are reported using a sanitized receiver
    label, never the raw source expression.
    """
    canonical = registry if registry is not None else build_capability_registry()
    root = Path(source_root) if source_root is not None else APP_ROOT
    base = Path(display_root) if display_root is not None else BACKEND_ROOT
    internal_names = {descriptor.name for descriptor in canonical.list_actions()}
    public_names = {
        descriptor.public_name or descriptor.name
        for descriptor in canonical.list_actions()
    }
    files = sorted(
        path for path in root.rglob("*.py") if "__pycache__" not in path.parts
    )
    calls: list[dict[str, Any]] = []
    for path in files:
        try:
            file = path.relative_to(base).as_posix()
        except ValueError:
            file = path.as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, UnicodeDecodeError) as exc:
            raise ValueError(
                f"Capability invocation source is not parseable: {file}"
            ) from exc
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            function = node.func
            if not isinstance(function, ast.Attribute):
                continue
            method = function.attr
            if method not in EXECUTE_METHODS:
                continue
            receiver = _receiver_label(function.value)
            if method == "execute" and _is_database_receiver(receiver):
                continue
            action_nodes = list(node.args[:1])
            action_nodes.extend(
                keyword.value for keyword in node.keywords if keyword.arg == "action"
            )
            found = [
                _literal_action(
                    action_node,
                    "action",
                    file=file,
                    method=method,
                    receiver=receiver,
                )
                for action_node in action_nodes
            ]
            if method == "_execute_capability":
                found.extend(
                    _literal_action(
                        keyword.value,
                        "public_action",
                        file=file,
                        method=method,
                        receiver=receiver,
                    )
                    for keyword in node.keywords
                    if keyword.arg == "public_action"
                )
            for call in found:
                if call is None:
                    continue
                valid_names = (
                    internal_names if call["kind"] == "action" else public_names
                )
                calls.append({**call, "registered": call["action"] in valid_names})
    calls.sort(key=lambda call: (call["file"], call["line"], call["column"]))
    unregistered = [call for call in calls if not call["registered"]]
    try:
        source = root.relative_to(base).as_posix()
    except ValueError:
        source = root.as_posix()
    return {
        "source_root": source,
        "scanned_files": len(files),
        "calls": calls,
        "unregistered": unregistered,
    }


def _has_required(schema: dict) -> bool:
    return (
        bool(schema.get("required"))
        or any(
            _has_required(child)
            for child in schema.get("properties", {}).values()
            if isinstance(child, dict)
        )
        or (isinstance(schema.get("items"), dict) and _has_required(schema["items"]))
    )


def required_paths(schema: dict, sample: Any, prefix: tuple = ()) -> list[tuple]:
    paths = []
    if isinstance(sample, dict):
        for name in schema.get("required", []):
            if name not in sample:
                raise ValueError(
                    f"Missing representative required value: {prefix + (name,)}"
                )
            paths.append(prefix + (name,))
        for name, child in schema.get("properties", {}).items():
            if name in sample:
                paths.extend(required_paths(child, sample[name], prefix + (name,)))
            elif _has_required(child):
                raise ValueError(f"Missing representative object: {prefix + (name,)}")
    elif isinstance(sample, list) and isinstance(schema.get("items"), dict):
        if not sample and _has_required(schema["items"]):
            raise ValueError(f"Need nonempty representative array: {prefix}")
        for index, child in enumerate(sample):
            paths.extend(required_paths(schema["items"], child, prefix + (index,)))
    for keyword in ("allOf", "anyOf", "oneOf"):
        if keyword in schema:
            # New branching schemas require explicit branch examples rather than
            # silently counting only whichever branch the fixture happens to hit.
            raise ValueError(
                f"Explicit branch fixtures required for {keyword}: {prefix}"
            )
    return paths


def path_label(path: tuple) -> str:
    return "/".join(str(part) for part in path)


def expected_observations(
    actions: dict[Key, ActionDescriptor], examples: dict[Key, Case]
) -> set[Observation]:
    expected = {(*key, scenario) for key in actions for scenario in SCENARIOS}
    registry = build_capability_registry()
    for key, descriptor in actions.items():
        owner = registry.find_action(key[0])
        if owner is not None and owner[0].name == "anime":
            expected.update((*key, scenario) for scenario in ANIME_SCENARIOS)
        elif owner is not None and owner[0].name == "subjects":
            expected.update((*key, scenario) for scenario in SUBJECTS_SCENARIOS)
        elif owner is not None and owner[0].name == "recommendation":
            expected.update((*key, scenario) for scenario in RECOMMENDATION_SCENARIOS)
        elif owner is not None and owner[0].name == "stats":
            expected.update((*key, scenario) for scenario in STATS_SCENARIOS)
        elif (
            owner is not None
            and owner[0].name == "collections"
            and not descriptor.is_side_effect
        ):
            expected.update((*key, scenario) for scenario in COLLECTIONS_READ_SCENARIOS)
        elif (
            owner is not None
            and owner[0].name == "schedule"
            and not descriptor.is_side_effect
        ):
            expected.update((*key, scenario) for scenario in SCHEDULE_READ_SCENARIOS)
        elif (
            owner is not None
            and owner[0].name == "media"
            and not descriptor.is_side_effect
        ):
            expected.update((*key, scenario) for scenario in MEDIA_READ_SCENARIOS)
        elif (
            owner is not None
            and owner[0].name == "collections"
            and descriptor.is_side_effect
        ):
            expected.update(
                (*key, scenario) for scenario in COLLECTIONS_WRITE_SCENARIOS
            )
        elif (
            owner is not None
            and owner[0].name == "schedule"
            and descriptor.is_side_effect
        ):
            expected.update((*key, scenario) for scenario in SCHEDULE_WRITE_SCENARIOS)
        elif (
            owner is not None and owner[0].name == "media" and descriptor.is_side_effect
        ):
            expected.update((*key, scenario) for scenario in MEDIA_WRITE_SCENARIOS)
        elif owner is not None and owner[0].name == "system":
            expected.update((*key, scenario) for scenario in SYSTEM_SCENARIOS)
        if key not in examples:
            continue  # fixture mismatch is a separate fatal diagnostic
        for path in required_paths(descriptor.input_schema, examples[key].arguments):
            expected.add((*key, "required:" + path_label(path)))
    return expected


def coverage_errors(expected: set[Observation], passed: set[Observation]) -> list[str]:
    errors = []
    if not expected:
        errors.append("Expected contract coverage is empty")
    for label, keys in (
        ("Missing executed", expected - passed),
        ("Unexpected", passed - expected),
    ):
        if keys:
            errors.append(
                f"{label} contracts: "
                + ", ".join(
                    f"{name}@{version}/{scenario}"
                    for name, version, scenario in sorted(keys)
                )
            )
    return errors


def fixture_errors(
    actions: dict[Key, ActionDescriptor], examples: dict[Key, Case]
) -> list[str]:
    errors = []
    if missing := set(actions) - set(examples):
        errors.append(f"Missing action fixtures: {sorted(missing)}")
    if stale := set(examples) - set(actions):
        errors.append(f"Stale action fixtures: {sorted(stale)}")
    return errors
