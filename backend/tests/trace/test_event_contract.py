"""Tests for TRACE-002 Step 01: event contract and redaction."""

from __future__ import annotations

import json
from time import perf_counter

from app.trace import AgentTrace, TraceStep, TraceEvent
import pytest

from app.trace.redaction import UnsafeTraceDataError, redact, sanitize_trace
from app.trace.recorder import TraceRecorder


class TestEventContract:
    def test_event_creation(self):
        evt = TraceEvent(
            event_type="node_start",
            data={"node": "think"},
            correlation_id="corr-1",
        )
        assert evt.event_type == "node_start"
        assert evt.correlation_id == "corr-1"
        assert evt.parent_event_id is None

    def test_event_with_parent(self):
        parent = TraceEvent(event_type="model_call", data={})
        child = TraceEvent(
            event_type="tool_call",
            data={"name": "search"},
            correlation_id=parent.correlation_id,
            parent_event_id=parent.event_id,
        )
        assert parent.event_id
        assert child.parent_event_id == parent.event_id
        assert child.correlation_id == parent.correlation_id

    def test_trace_steps_serialize_deterministically(self):
        trace = AgentTrace(task_id=1, goal="test")
        step = TraceStep(step_index=0, step_label="search", agent_name="AnimeAgent")
        step.events.append(
            TraceEvent(event_type="capability_call", data={"action": "search"})
        )
        trace.add_step(step)
        trace.mark_completed()

        data = trace.model_dump(mode="json")
        reloaded = json.loads(json.dumps(data))
        assert len(reloaded["steps"]) == 1
        assert reloaded["steps"][0]["events"][0]["event_type"] == "capability_call"

    def test_trace_recorder_assigns_shared_ids_and_safe_payload_metadata(self):
        trace = AgentTrace(run_id="run-1", agent_name="agent")
        recorder = TraceRecorder(trace)

        first = recorder.record(
            "model_call",
            "model.complete",
            {
                "provider": "fake",
                "model": "model-v1",
                "usage": {
                    "total_tokens": 12,
                    "prompt": "private prompt",
                },
                "invocation_id": "inv-1",
                "content": "private prompt",
            },
        )
        second = recorder.record("tool_call", "search", {"content": "private result"})

        assert first.run_id == "run-1"
        assert second.run_id == "run-1"
        assert first.sequence == 1
        assert second.sequence == 2
        assert first.invocation_id == "inv-1"
        assert first.provider == "fake"
        assert first.model == "model-v1"
        assert first.usage["total_tokens"] == 12
        assert "prompt" not in first.usage
        assert first.data["content"]["length"] == len("private prompt")
        assert "sha256" in first.data["content"]
        assert "private prompt" not in trace.model_dump_json()


class TestRedaction:
    def test_secret_keys_redacted(self):
        payload = {
            "api_key": "sk-123456",
            "query": "hello",
            "authorization": "Bearer xyz",
        }
        result = redact(payload)
        assert result["api_key"] == "[REDACTED]"
        assert result["authorization"] == "[REDACTED]"
        assert result["query"] == "hello"

    def test_case_insensitive_secret_redaction(self):
        payload = {"API_KEY": "secret", "Api-Key": "also-secret"}
        result = redact(payload)
        assert result["API_KEY"] == "[REDACTED]"
        assert result["Api-Key"] == "[REDACTED]"

    def test_nested_secret_redaction(self):
        payload = {"config": {"api_key": "sk-789", "model": "gpt-4"}}
        result = redact(payload)
        assert result["config"]["api_key"] == "[REDACTED]"
        assert result["config"]["model"] == "gpt-4"

    def test_chain_of_thought_dropped(self):
        payload = {"response": "ok", "chain_of_thought": "secret reasoning"}
        result = redact(payload)
        assert "chain_of_thought" not in result
        assert result["response"] == "ok"

    def test_reasoning_trace_dropped(self):
        payload = {"output": "final", "reasoning_trace": "step by step"}
        result = redact(payload)
        assert "reasoning_trace" not in result

    def test_long_string_truncated(self):
        long_str = "a" * 3000
        payload = {"content": long_str}
        result = redact(payload)
        assert len(result["content"]) <= 2000 + len("... (truncated)")

    def test_large_list_truncated(self):
        payload = {"items": list(range(500))}
        result = redact(payload)
        assert len(result["items"]) == 200

    def test_large_mapping_truncated(self):
        result = redact({f"key-{index}": index for index in range(500)})
        assert len(result) == 200

    def test_hyphenated_secret_variants_redacted(self):
        result = redact({"x-api-key": "secret", "x-api-token": "token"})
        assert result == {
            "x-api-key": "[REDACTED]",
            "x-api-token": "[REDACTED]",
        }

    def test_trace_sanitizer_redacts_private_goal(self):
        trace = AgentTrace(goal="private prompt")
        sanitized = sanitize_trace(trace)
        assert sanitized.goal == "[REDACTED]"

    def test_trace_sanitizer_rejects_chain_of_thought(self):
        trace = AgentTrace()
        step = TraceStep(step_index=0, step_label="model", agent_name="agent")
        step.events.append(
            TraceEvent(
                event_type="model_call",
                data={"chain_of_thought": "do not persist"},
            )
        )
        trace.add_step(step)

        with pytest.raises(UnsafeTraceDataError):
            sanitize_trace(trace)

    def test_no_real_secrets_in_serialized_output(self):
        """Automated fixture: prove secrets never appear in serialized trace."""
        payload = {
            "api_key": "sk-test123",
            "headers": {"authorization": "Bearer test"},
            "data": [{"secret": "nested-password", "name": "public"}],
        }
        result = redact(payload)
        serialized = json.dumps(result)
        assert "[REDACTED]" in serialized
        assert "sk-test123" not in serialized
        assert "nested-password" not in serialized
        assert "Bearer test" not in serialized
        assert "public" in serialized


def test_trace_recorder_event_overhead_is_bounded():
    trace = AgentTrace(agent_name="benchmark")
    recorder = TraceRecorder(trace)
    event_count = 200

    started = perf_counter()
    for index in range(event_count):
        recorder.record(
            "node_start",
            "benchmark.node",
            {"index": index},
        )
    elapsed = perf_counter() - started

    assert elapsed / event_count < 0.005
