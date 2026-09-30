"""Tests for the provider-neutral stream event projection."""

from app.harness.coordinator import RunCoordinator


def test_stream_event_projection_redacts_tool_values():
    coordinator = RunCoordinator(object())
    event = coordinator._record_event(
        {
            "type": "tool_call_end",
            "invocation_id": "call-1",
            "capability": "catalog.search",
            "status": "succeeded",
            "output": {"secret": "must not persist"},
        },
        "run-1",
    )

    assert event is not None
    assert event.event_type == "tool_call_end"
    assert event.invocation_id == "call-1"
    assert event.payload == {
        "name": "catalog.search",
        "status": "succeeded",
    }
    assert "must not persist" not in event.model_dump_json()


def test_stream_event_projection_assigns_safe_argument_shape():
    coordinator = RunCoordinator(object())
    event = coordinator._record_event(
        {
            "type": "tool_call_start",
            "invocation_id": "call-1",
            "capability": "catalog.search",
            "arguments": {"query": "private"},
        },
        "run-1",
    )

    assert event is not None
    assert event.payload == {
        "name": "catalog.search",
        "argument_keys": ["query"],
    }
