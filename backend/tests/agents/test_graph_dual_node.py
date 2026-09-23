"""Regression coverage for the canonical Runtime event vocabulary."""

from app.harness.coordinator import RunCoordinator


def test_runtime_event_projection_preserves_decision_shape_only():
    coordinator = RunCoordinator(object())
    event = coordinator._record_event(
        {
            "type": "model_decision",
            "action": "invoke",
            "capability": "catalog.search",
            "capability_version": "v1",
            "argument_keys": ["query"],
            "arguments": {"query": "not persisted"},
        },
        "run-1",
    )

    assert event is not None
    assert event.payload == {
        "action": "invoke",
        "capability": "catalog.search",
        "capability_version": "v1",
        "argument_keys": ["query"],
    }
    assert "not persisted" not in event.model_dump_json()
