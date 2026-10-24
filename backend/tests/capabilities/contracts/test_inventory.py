"""The census must include writes and every descriptor's own version."""

import importlib.util


def test_contract_inventory_is_implemented():
    assert importlib.util.find_spec("tests.capabilities.contracts.catalog"), (
        "Missing Registry-driven contract inventory and coverage diagnostics"
    )


def test_execution_gate_is_implemented():
    assert importlib.util.find_spec("tests.capabilities.contracts.plugin"), (
        "Missing execution-based contract CI gate"
    )


def test_census_keeps_writes_and_descriptor_versions():
    from app.capabilities.registry import CapabilityRegistry
    from tests.harness.test_dispatcher import FakeCapability
    from dataclasses import replace
    from tests.capabilities.contracts.catalog import census

    registry = CapabilityRegistry()
    capability = FakeCapability(side_effect=True)
    capability._descriptor = replace(capability._descriptor, version="v2")
    registry.register(capability)
    assert set(census(registry)) == {("catalog.write", "v2")}


def test_missing_stale_and_empty_coverage_fail_closed():
    from tests.capabilities.contracts.catalog import coverage_errors

    assert coverage_errors({("new", "v2", "success")}, set()) == [
        "Missing executed contracts: new@v2/success"
    ]
    assert "empty" in coverage_errors(set(), set())[0].lower()
    assert "Unexpected" in coverage_errors(set(), {("old", "v1", "success")})[-1]


def test_nested_required_needs_nonempty_representative_input():
    import pytest
    from tests.capabilities.contracts.catalog import required_paths

    schema = {
        "properties": {
            "items": {
                "items": {
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                }
            }
        },
        "required": ["items"],
    }
    assert required_paths(schema, {"items": [{"name": "x"}]}) == [
        ("items",),
        ("items", 0, "name"),
    ]
    with pytest.raises(ValueError, match="representative"):
        required_paths(schema, {"items": []})
