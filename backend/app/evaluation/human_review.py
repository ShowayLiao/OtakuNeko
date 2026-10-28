"""Versioned human review records attached to evaluation cases."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from app.evaluation.types import HumanReview


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HumanReviewFile(_StrictModel):
    schema_version: int = 1
    dataset_version: str
    cases: dict[str, HumanReview] = Field(default_factory=dict)


def load_human_reviews(
    path: str | Path,
    dataset_version: str,
) -> dict[str, HumanReview]:
    """Load reviewer conclusions; missing files and version drift fail closed."""
    review_path = Path(path)
    if not review_path.is_file():
        raise ValueError("human review file missing")
    try:
        payload = HumanReviewFile.model_validate_json(
            review_path.read_text(encoding="utf-8")
        )
    except Exception as exc:
        raise ValueError("human review file invalid") from exc
    if payload.schema_version != 1:
        raise ValueError("human review schema unsupported")
    if payload.dataset_version != dataset_version:
        raise ValueError("human review dataset version mismatch")
    return payload.cases
