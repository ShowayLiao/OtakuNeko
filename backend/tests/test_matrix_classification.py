import pytest

from tests.matrix_plugin import classify_item


def test_api_directory_is_integration_and_api_marked() -> None:
    classification = classify_item(
        "tests/api/test_collections.py::test_list",
        (),
        (),
    )

    assert classification.tier == "integration"
    assert classification.dimensions == {"integration", "api"}


def test_database_fixture_closure_adds_integration_and_db_marks() -> None:
    classification = classify_item(
        "tests/harness/test_store.py::test_round_trip",
        ("db_session",),
        (),
    )

    assert classification.tier == "integration"
    assert classification.dimensions == {"integration", "db"}


def test_postgres_fixture_closure_adds_postgres_dimension() -> None:
    classification = classify_item(
        "tests/harness/test_store.py::test_postgres",
        ("postgres_session",),
        (),
    )

    assert classification.tier == "integration"
    assert classification.dimensions == {"integration", "db", "postgres"}


def test_postgres_marker_implies_integration_and_db() -> None:
    classification = classify_item(
        "tests/harness/test_schema.py::test_cleanup",
        (),
        ("postgres",),
    )

    assert classification.tier == "integration"
    assert classification.dimensions == {"integration", "db", "postgres"}


def test_db_marker_implies_integration() -> None:
    classification = classify_item(
        "tests/memory/test_migration.py::test_upgrade",
        (),
        ("db",),
    )

    assert classification.tier == "integration"
    assert classification.dimensions == {"integration", "db"}


def test_api_marker_implies_integration() -> None:
    classification = classify_item(
        "tests/harness/test_route.py::test_route",
        (),
        ("api",),
    )

    assert classification.tier == "integration"
    assert classification.dimensions == {"integration", "api"}


def test_explicit_unit_tier_overrides_directory_default() -> None:
    classification = classify_item(
        "tests/services/test_pure.py::test_mapping",
        (),
        ("unit",),
    )

    assert classification.tier == "unit"
    assert classification.dimensions == {"unit"}


def test_explicit_integration_tier_overrides_unit_default() -> None:
    classification = classify_item(
        "tests/harness/test_contract.py::test_contract",
        (),
        ("integration",),
    )

    assert classification.tier == "integration"
    assert classification.dimensions == {"integration"}


def test_client_fixture_marks_api_and_forces_integration() -> None:
    classification = classify_item(
        "tests/harness/test_http.py::test_request",
        ("api_client",),
        (),
    )

    assert classification.tier == "integration"
    assert classification.dimensions == {"integration", "api"}


def test_external_http_fixture_forces_integration() -> None:
    classification = classify_item(
        "tests/services/test_client.py::test_request",
        ("external_http",),
        (),
    )

    assert classification.tier == "integration"
    assert classification.dimensions == {"integration"}


def test_existing_dimensions_are_preserved() -> None:
    classification = classify_item(
        "tests/test_unit.py::test_value",
        (),
        ("unit", "db"),
    )

    assert classification.tier == "unit"
    assert classification.dimensions == {"unit", "db"}


def test_explicit_unit_overrides_database_dimension_tier_inference() -> None:
    classification = classify_item(
        "tests/test_unit.py::test_database_shape",
        (),
        ("unit", "db"),
    )

    assert classification.tier == "unit"
    assert classification.dimensions == {"unit", "db"}


def test_conflicting_explicit_tiers_are_rejected() -> None:
    with pytest.raises(pytest.UsageError, match="both unit and integration"):
        classify_item(
            "tests/test_conflict.py::test_value",
            (),
            ("unit", "integration"),
        )
