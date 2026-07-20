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

    def test_side_effecting_actions_are_distinguishable(self):
        read = ActionDescriptor("read", "r", input_schema={}, is_side_effect=False)
        write = ActionDescriptor("write", "w", input_schema={}, is_side_effect=True)
        assert not read.is_side_effect
        assert write.is_side_effect

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
