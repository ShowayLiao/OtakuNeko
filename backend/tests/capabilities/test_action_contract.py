"""Tests for CAPABILITY-002: action contract types."""

import json
import pytest
from dataclasses import FrozenInstanceError

from app.capabilities.types import ActionDescriptor, CapabilityResult


class TestActionDescriptor:
    def test_to_dict_is_json_serializable(self):
        desc = ActionDescriptor(
            name="test_action",
            description="A test action",
            input_schema={"type": "object", "properties": {"x": {"type": "string"}}},
            requires_auth=True,
            is_side_effect=False,
        )
        d = desc.to_dict()
        assert json.dumps(d)
        assert d["name"] == "test_action"
        assert d["requires_auth"] is True
        assert d["is_side_effect"] is False

    def test_model_json_schema_returns_input_schema(self):
        schema = {"type": "object", "properties": {}}
        desc = ActionDescriptor("a", "desc", input_schema=schema)
        assert desc.model_json_schema() is schema

    def test_defaults_are_false(self):
        desc = ActionDescriptor("a", "desc", input_schema={})
        assert desc.requires_auth is False
        assert desc.is_side_effect is False
        assert desc.version == "v1"
        assert desc.risk_level == "low"
        assert desc.approval_required is False
        assert desc.output_schema["type"] == "object"

    def test_side_effecting_actions_are_distinguishable(self):
        read = ActionDescriptor("read", "r", input_schema={}, is_side_effect=False)
        write = ActionDescriptor("write", "w", input_schema={}, is_side_effect=True)
        assert not read.is_side_effect
        assert write.is_side_effect
        assert write.approval_required is True

    def test_versioned_public_metadata_is_serializable(self):
        desc = ActionDescriptor(
            "read",
            "read data",
            input_schema={"type": "object", "properties": {}},
            version="v2",
            output_schema={"type": "object", "properties": {"value": {"type": "string"}}},
            risk_level="medium",
            timeout_seconds=12,
            retry_class="transient",
            idempotency_mode="keyed",
            approval_required=True,
        )
        data = desc.to_dict()
        assert json.dumps(data)
        assert data["version"] == "v2"
        assert data["timeout_seconds"] == 12
        assert data["idempotency_mode"] == "keyed"

    def test_descriptor_is_immutable(self):
        desc = ActionDescriptor("a", "desc", input_schema={})
        with pytest.raises(FrozenInstanceError):
            desc.name = "changed"


class TestCapabilityResult:
    def test_ok_creates_success_result(self):
        r = CapabilityResult.ok(key="value")
        d = r.to_dict()
        assert d["success"] is True
        assert d["key"] == "value"
        assert "error" not in d

    def test_fail_creates_typed_error(self):
        r = CapabilityResult.fail("not found", error_type="not_found")
        d = r.to_dict()
        assert d["success"] is False
        assert d["error"] == "not found"
        assert d["error_type"] == "not_found"

    def test_fail_includes_extra_data(self):
        r = CapabilityResult.fail("bad", error_type="invalid", detail="x required")
        d = r.to_dict()
        assert d["error"] == "bad"
        assert d["detail"] == "x required"

    def test_to_dict_is_json_serializable(self):
        r = CapabilityResult.ok(count=5, items=[])
        d = r.to_dict()
        assert json.dumps(d)

    def test_to_safe_dict_uses_structured_data_envelope(self):
        result = CapabilityResult.ok(value="safe")
        assert result.to_safe_dict() == {"success": True, "data": {"value": "safe"}}

    def test_to_safe_dict_rejects_invalid_or_oversized_payload(self):
        result = CapabilityResult.ok(value="too-large")
        invalid = result.to_safe_dict(
            output_schema={"type": "object", "required": ["missing"]}
        )
        oversized = result.to_safe_dict(max_payload_bytes=10)
        assert invalid["success"] is False
        assert invalid["error_type"] == "invalid_output"
        assert oversized["success"] is False
        assert oversized["error_type"] == "payload_too_large"
