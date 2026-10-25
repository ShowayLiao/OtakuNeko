"""Controlled external responses for live-model evaluation.

The production Runtime, registry, dispatcher and capabilities stay real. This
module only replaces provider/service calls that would otherwise leave the
process, and the evaluation allowlist prevents the model from reaching any
capability that is not either DB/local-only or covered by a fixture here.
"""

from __future__ import annotations

from collections.abc import Collection, Iterator
from contextlib import contextmanager
import copy
from typing import Any
from unittest.mock import patch

CONTROLLED_FIXTURE_PROFILE = "controlled-v1"

# Every entry is either local/DB-backed or patched by this module. Adding a
# capability here without a fixture would allow an unplanned external call.
CONTROLLED_ALLOWED_CAPABILITIES = frozenset(
    {
        "get_current_time",
        "list_collections",
        "get_collection_statistics",
        "search_anime_advanced",
    }
)

_FIXED_ANIME_SEARCH: dict[str, Any] = {
    "data": [
        {
            "id": 400602,
            "name": "Sousou no Frieren",
            "name_cn": "Frieren: Beyond Journey's End",
            "summary": "Controlled evaluation fixture for search responses.",
            "rating": {"score": 9.0, "rank": 1},
            "type": 2,
            "air_date": "2023-09-29",
            "images": {},
            "tags": [{"name": "fantasy"}, {"name": "adventure"}],
        }
    ],
    "total": 1,
}


def controlled_allowed_capabilities(profile: str) -> frozenset[str]:
    """Return the fixed read-only capability set for a fixture profile."""
    if profile != CONTROLLED_FIXTURE_PROFILE:
        raise ValueError("unsupported controlled fixture profile")
    return CONTROLLED_ALLOWED_CAPABILITIES


def validate_controlled_capabilities(
    profile: str,
    names: Collection[str],
) -> frozenset[str]:
    """Fail closed when a configured capability has no controlled fixture."""
    allowed = controlled_allowed_capabilities(profile)
    requested = frozenset(names)
    if not requested:
        raise ValueError("controlled evaluation requires allowed capabilities")
    unsupported = sorted(requested - allowed)
    if unsupported:
        raise ValueError(
            "controlled capability is not fixture-backed: " + ", ".join(unsupported)
        )
    return requested


async def _fixed_search_subjects_advanced(**_kwargs: Any) -> dict[str, Any]:
    return copy.deepcopy(_FIXED_ANIME_SEARCH)


@contextmanager
def controlled_external_responses(profile: str | None) -> Iterator[None]:
    """Install fixed external responses; no request leaves the process."""
    if profile is None:
        yield
        return
    validate_controlled_capabilities(profile, CONTROLLED_ALLOWED_CAPABILITIES)
    with patch(
        "app.capabilities.anime.search_subjects_advanced",
        _fixed_search_subjects_advanced,
    ):
        yield
