"""Versioned JSONL dataset loading and validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.evaluation.types import DatasetManifest, EvalCase, EvalDataset


def _objects(path: Path) -> list[tuple[int, dict[str, Any]]]:
    objects: list[tuple[int, dict[str, Any]]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, 1):
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
    objects = _objects(dataset_path)
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

    return EvalDataset(
        dataset_version=manifest.dataset_version,
        schema_version=manifest.schema_version,
        cases=cases,
    )
