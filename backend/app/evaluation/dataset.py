"""Versioned JSONL dataset loading and validation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.evaluation.types import DatasetManifest, EvalCase, EvalDataset


def _objects(path: Path, text: str) -> list[tuple[int, dict[str, Any]]]:
    objects: list[tuple[int, dict[str, Any]]] = []
    for line_number, raw in enumerate(text.split("\n"), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_number}: expected a JSON object")
        objects.append((line_number, value))
    return objects


def load_dataset(path: str | Path) -> EvalDataset:
    dataset_path = Path(path)
    # Read once so the parsed cases and the digest come from the same bytes.
    # Text mode normalizes CRLF/CR to LF, keeping the digest stable across
    # Windows/Linux checkouts (core.autocrlf may rewrite line endings).
    content = dataset_path.read_text(encoding="utf-8")
    objects = _objects(dataset_path, content)
    if not objects:
        raise ValueError(f"{dataset_path}: missing dataset manifest")

    manifest_line, manifest_raw = objects[0]
    if "dataset_version" not in manifest_raw:
        raise ValueError(
            f"{dataset_path}:{manifest_line}: first object must be dataset manifest"
        )
    try:
        manifest = DatasetManifest.model_validate(manifest_raw)
    except ValidationError as exc:
        raise ValueError(f"{dataset_path}:{manifest_line}: {exc}") from exc

    cases: list[EvalCase] = []
    seen: set[str] = set()
    for line_number, raw in objects[1:]:
        try:
            case = EvalCase.model_validate(raw)
        except ValidationError as exc:
            raise ValueError(f"{dataset_path}:{line_number}: {exc}") from exc
        if case.id in seen:
            raise ValueError(
                f"{dataset_path}:{line_number}: Duplicate case id '{case.id}'"
            )
        seen.add(case.id)
        cases.append(case)

    content_digest = hashlib.sha256(content.encode("utf-8")).hexdigest()

    return EvalDataset(
        dataset_version=manifest.dataset_version,
        schema_version=manifest.schema_version,
        content_digest=content_digest,
        cases=cases,
    )
