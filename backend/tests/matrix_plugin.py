"""Automatic test-tier and execution-dimension classification."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Iterable

import pytest


_INTEGRATION_DIRECTORIES = (
    "/api/",
    "/acceptance/",
    "/repositories/",
    "/services/",
    "/proactive/",
)
_DATABASE_FIXTURES = {
    "db_session",
    "sqlite_engine",
    "postgres_engine",
    "postgres_session",
    "temp_db_path",
}
_API_FIXTURES = {"api_app", "api_client"}
_INTEGRATION_FIXTURES = _DATABASE_FIXTURES | _API_FIXTURES | {"external_http"}


@dataclass(frozen=True)
class Classification:
    tier: str
    dimensions: set[str]


def classify_item(
    nodeid: str,
    fixture_names: Iterable[str],
    existing_markers: Iterable[str],
) -> Classification:
    """Return the inferred tier and dimensions for one collected test.

    ``unit`` and ``integration`` are mutually exclusive tier markers. Any
    explicitly supplied tier marker wins over the directory and fixture
    heuristics; orthogonal ``db`` and ``api`` dimensions are still inferred.
    """

    fixtures = set(fixture_names)
    markers = set(existing_markers)
    explicit_tiers = markers & {"unit", "integration"}
    if len(explicit_tiers) > 1:
        raise pytest.UsageError(
            f"Test {nodeid!r} cannot request both unit and integration markers"
        )

    if explicit_tiers:
        tier = "integration" if "integration" in explicit_tiers else "unit"
    elif (
        any(
            directory in f"/{nodeid.replace(chr(92), '/')}"
            for directory in _INTEGRATION_DIRECTORIES
        )
        or fixtures & _INTEGRATION_FIXTURES
        or markers & {"db", "api", "postgres"}
    ):
        tier = "integration"
    else:
        tier = "unit"

    dimensions = (set(explicit_tiers) if explicit_tiers else {tier}) | (
        markers & {"db", "api", "postgres"}
    )
    if "postgres" in markers:
        dimensions.add("db")
    if fixtures & _DATABASE_FIXTURES:
        dimensions.add("db")
    if fixtures & {"postgres_engine", "postgres_session"}:
        dimensions.add("postgres")
    if "/api/" in f"/{nodeid.replace(chr(92), '/')}":
        dimensions.add("api")
    if fixtures & _API_FIXTURES:
        dimensions.add("api")
    return Classification(tier=tier, dimensions=dimensions)


def pytest_collection_modifyitems(config, items) -> None:
    """Apply classification markers after pytest resolves fixture closure."""

    for item in items:
        existing = {marker.name for marker in item.iter_markers()}
        classification = classify_item(item.nodeid, item.fixturenames, existing)
        for marker in sorted(classification.dimensions - existing):
            item.add_marker(getattr(pytest.mark, marker))


def pytest_collection_finish(session) -> None:
    """Store compact marker counts for the terminal summary."""

    session.config._otakuneko_matrix_counts = {
        marker: sum(
            item.get_closest_marker(marker) is not None for item in session.items
        )
        for marker in ("unit", "integration", "db", "api", "postgres")
    }


def pytest_terminal_summary(terminalreporter, exitstatus, config) -> None:
    counts = getattr(config, "_otakuneko_matrix_counts", None)
    if counts is None:
        return
    terminalreporter.write_sep("-", "test matrix")
    terminalreporter.write_line(
        "matrix counts: " + ", ".join(f"{marker}={counts[marker]}" for marker in counts)
    )
