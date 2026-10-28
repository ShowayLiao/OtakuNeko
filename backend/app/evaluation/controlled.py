"""Controlled external responses for live-model evaluation.

The production Runtime, registry, dispatcher and capabilities stay real. This
module only replaces provider/service calls that would otherwise leave the
process, and the evaluation allowlist prevents the model from reaching any
capability that is not either DB/local-only or covered by a fixture here.
"""

from __future__ import annotations

from collections.abc import Collection, Iterator, Mapping
from contextlib import contextmanager
import copy
import re
from typing import Any
from unittest.mock import patch

from app.evaluation.anime_fixtures import AnimeFixtureSet

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
    if profile == "controlled-task-v1":
        # Profile generation reads only the isolated case database and computes
        # locally. External anime search still uses the same fixed response.
        # Collection updates are safe here only because each live benchmark
        # case uses a fresh in-memory database and a trusted approval fixture.
        return CONTROLLED_ALLOWED_CAPABILITIES | {
            "generate_user_profile_tool",
            "update_collection",
        }
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


class ControlledAnimeSearch:
    """Fixture-backed search adapter with observable, one-shot tool faults."""

    def __init__(
        self,
        fixture_set: AnimeFixtureSet,
        tool_faults: Collection[Mapping[str, Any]] = (),
    ) -> None:
        self._fixture_set = fixture_set
        self._faults = [dict(fault) for fault in tool_faults]
        self.search_call_count = 0
        self.triggered_faults: list[str] = []
        self._triggered_fault_indexes: set[int] = set()
        self._timeout_call_count: int | None = None
        self.successful_search_subject_ids_after_fault: set[str] = set()
        for fault in self._faults:
            if (
                fault.get("target") != "anime_search"
                or type(fault.get("occurrence")) is not int
                or fault["occurrence"] < 1
                or fault.get("mode") not in {"timeout_once", "inject_untrusted_snippet"}
            ):
                raise ValueError("unsupported anime benchmark tool fault")
            if fault["mode"] == "timeout_once" and not fault.get(
                "recover_on_next_attempt"
            ):
                raise ValueError("timeout fault must recover on the next attempt")
            if (
                fault["mode"] == "inject_untrusted_snippet"
                and fault.get("fixture_key") != "malicious_result"
            ):
                raise ValueError("unsupported anime benchmark attack fixture")

    async def search(self, **kwargs: Any) -> dict[str, Any]:
        self.search_call_count += 1
        fault = self._fault_for_occurrence(self.search_call_count)
        if fault is not None and fault["mode"] == "timeout_once":
            self._mark_fault(fault)
            raise TimeoutError("synthetic anime search timeout")

        rows = self._search_rows(kwargs)
        offset = max(0, int(kwargs.get("offset") or 0))
        limit = max(1, min(100, int(kwargs.get("limit") or 10)))
        page = rows[offset : offset + limit]
        if fault is not None and fault["mode"] == "inject_untrusted_snippet" and page:
            self._inject_untrusted_snippet(page)
            self._mark_fault(fault)
        if (
            self._timeout_call_count is not None
            and self.search_call_count > self._timeout_call_count
        ):
            self.successful_search_subject_ids_after_fault.update(
                subject_id
                for row in page
                if (subject_id := self._benchmark_subject_id(row)) is not None
            )
        return {"data": page, "total": len(rows)}

    def _fault_for_occurrence(self, occurrence: int) -> dict[str, Any] | None:
        for index, fault in enumerate(self._faults):
            if index in self._triggered_fault_indexes:
                continue
            if fault["occurrence"] == occurrence:
                return {**fault, "_index": index}
        return None

    def _mark_fault(self, fault: Mapping[str, Any]) -> None:
        index = int(fault["_index"])
        self._triggered_fault_indexes.add(index)
        self.triggered_faults.append(str(fault["mode"]))
        if fault["mode"] == "timeout_once":
            self._timeout_call_count = self.search_call_count

    @staticmethod
    def _benchmark_subject_id(row: Mapping[str, Any]) -> str | None:
        summary = str(row.get("summary") or "")
        match = re.search(r"\bbenchmark_id=(AC[0-9]+);", summary)
        return match.group(1) if match else None

    def _search_rows(self, kwargs: Mapping[str, Any]) -> list[dict[str, Any]]:
        query = str(kwargs.get("keyword") or "").strip().casefold()
        requested_tags = {
            str(tag).casefold() for tag in (kwargs.get("tags") or []) if tag
        }
        anime_entries = list(self._fixture_set.catalog["anime"])
        scored: list[tuple[int, dict[str, Any]]] = []
        for anime in anime_entries:
            title = str(anime["title"])
            aliases = [str(alias) for alias in anime.get("aliases", ())]
            tags = [str(tag) for tag in anime.get("tags", ())]
            searchable = [title, *aliases]
            title_hit = bool(query) and any(
                query in value.casefold() or value.casefold() in query
                for value in searchable
            )
            tag_hit = bool(query) and any(
                tag.casefold() in query or query in tag.casefold() for tag in tags
            )
            requested_tag_hit = bool(requested_tags) and bool(
                requested_tags & {tag.casefold() for tag in tags}
            )
            any_hit = title_hit or tag_hit or requested_tag_hit
            score = 0 if title_hit else 1 if (tag_hit or requested_tag_hit) else 2
            if any_hit or not query and not requested_tags:
                scored.append((score, self._to_search_row(anime)))
        if not scored:
            scored = [(2, self._to_search_row(anime)) for anime in anime_entries]
        return [
            row for _, row in sorted(scored, key=lambda item: (item[0], item[1]["id"]))
        ]

    def _to_search_row(self, anime: Mapping[str, Any]) -> dict[str, Any]:
        anime_id = str(anime["id"])
        local_id = int(re.search(r"([0-9]+)$", anime_id).group(1))
        summary_parts = [
            f"benchmark_id={anime_id};",
            f"episodes={anime.get('episodes')};",
            f"tags={','.join(str(tag) for tag in anime.get('tags', ()))};",
            f"gore_level={anime.get('gore_level', 0)};",
            f"horror={str(bool(anime.get('horror', False))).lower()};",
        ]
        if anime.get("franchise"):
            summary_parts.extend(
                [
                    f"franchise={anime['franchise']};",
                    f"story_order={anime.get('story_order')};",
                ]
            )
        references = self._fixture_set.search_snapshots["results"].get(anime_id, ())
        if references:
            refs = "; ".join(
                f"[{ref['source_id']}] {ref['title']} ({ref.get('publisher', 'unknown publisher')})"
                for ref in references[:3]
            )
            summary_parts.append(f"source_references={refs};")
        return {
            "id": 900000 + local_id,
            "name": anime["title"],
            "name_cn": anime["title"],
            "summary": " ".join(summary_parts),
            "rating": {"score": 0, "rank": 0},
            "type": 2,
            "air_date": "2026-01-01",
            "images": {},
            "tags": [{"name": str(tag)} for tag in anime.get("tags", ())],
        }

    def _inject_untrusted_snippet(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        attack = self._fixture_set.search_snapshots["malicious_result"]["text"]
        row = rows[0]
        row["summary"] = f"{row.get('summary', '')} {attack}".strip()


async def _fixed_search_subjects_advanced(**_kwargs: Any) -> dict[str, Any]:
    return copy.deepcopy(_FIXED_ANIME_SEARCH)


@contextmanager
def controlled_external_responses(
    profile: str | None,
    *,
    anime_fixture_set: AnimeFixtureSet | None = None,
    tool_faults: Collection[Mapping[str, Any]] = (),
) -> Iterator[ControlledAnimeSearch | None]:
    """Install fixed external responses; no request leaves the process."""
    if profile is None:
        if anime_fixture_set is not None or tool_faults:
            raise ValueError("anime benchmark fixtures require a controlled profile")
        yield
        return
    validate_controlled_capabilities(profile, CONTROLLED_ALLOWED_CAPABILITIES)
    if anime_fixture_set is None:
        with patch(
            "app.capabilities.anime.search_subjects_advanced",
            _fixed_search_subjects_advanced,
        ):
            yield None
        return

    controlled_search = ControlledAnimeSearch(anime_fixture_set, tool_faults)
    with patch(
        "app.capabilities.anime.search_subjects_advanced",
        controlled_search.search,
    ):
        yield controlled_search
