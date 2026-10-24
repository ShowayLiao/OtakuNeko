"""Discovery tests for MCP-002: exposure validation and schema startup checks."""

from __future__ import annotations

import pytest

from app.capabilities.anime import AnimeCapability
from app.capabilities.schedule import ScheduleCapability
from app.capabilities.registry import CapabilityRegistry
from app.capabilities.types import ActionDescriptor
from app.mcp_server import MCPServer, ExposureMap, _validate_exposure_map


class TestExposureMap:
    """ExposureMap filtering and validation."""

    def test_exposed_actions(self):
        exposure = ExposureMap({"anime": ["search", "get_detail"]})
        assert exposure.is_exposed("anime", "search") is True
        assert exposure.is_exposed("anime", "get_detail") is True
        assert exposure.is_exposed("anime", "get_staff") is False
        assert exposure.is_exposed("bogus", "any") is False

    def test_empty_exposure_hides_everything(self):
        exposure = ExposureMap({})
        assert exposure.is_exposed("anime", "search") is False

    def test_exposed_actions_filters_registered_actions(self):
        cap = AnimeCapability()
        exposure = ExposureMap({"anime": ["search", "get_detail"]})
        actions = exposure.exposed_actions("anime", cap)
        names = {a.name for a in actions}
        assert names == {"search", "get_detail"}


class TestExposureValidation:
    """Startup validation checks."""

    def test_valid_exposure_passes(self):
        registry = CapabilityRegistry()
        registry.register(AnimeCapability())
        exposure = ExposureMap({"anime": ["search", "get_detail"]})
        # Should not raise
        _validate_exposure_map(registry, exposure)

    def test_unknown_capability_raises(self):
        registry = CapabilityRegistry()
        registry.register(AnimeCapability())
        exposure = ExposureMap({"nonexistent": ["action"]})
        with pytest.raises(ValueError, match="unknown capability"):
            _validate_exposure_map(registry, exposure)

    def test_unknown_action_raises(self):
        registry = CapabilityRegistry()
        registry.register(AnimeCapability())
        exposure = ExposureMap({"anime": ["bogus_action"]})
        with pytest.raises(ValueError, match="no action"):
            _validate_exposure_map(registry, exposure)

    def test_duplicate_public_name_raises(self):
        """Duplicate MCP tool names from the same capability are caught."""
        registry = CapabilityRegistry()
        registry.register(AnimeCapability())
        # List the same action twice under the same capability — produces
        # duplicate public names when iterating.
        exposure = ExposureMap({"anime": ["search", "search"]})
        with pytest.raises(ValueError, match="Duplicate public"):
            _validate_exposure_map(registry, exposure)

    def test_server_with_no_exposure_lists_nothing(self):
        registry = CapabilityRegistry()
        registry.register(AnimeCapability())
        server = MCPServer(registry)  # no exposure = empty
        assert server.list_tools() == []

    def test_authenticated_identity_field_is_not_public(self):
        registry = CapabilityRegistry()
        registry.register(ScheduleCapability())
        server = MCPServer(
            registry,
            ExposureMap({"schedule": ["list_schedules"]}),
        )

        schema = server.list_tools()[0]["inputSchema"]

        assert "user_id" not in schema["properties"]
        assert "user_id" not in schema.get("required", [])

    def test_invalid_input_schema_fails_startup(self, monkeypatch):
        capability = AnimeCapability()
        invalid = ActionDescriptor(
            name="search",
            description="invalid schema",
            input_schema={
                "type": "object",
                "properties": {},
                "required": ["missing"],
            },
        )
        monkeypatch.setattr(capability, "actions", lambda: [invalid])
        registry = CapabilityRegistry()
        registry.register(capability)

        with pytest.raises(ValueError, match="unknown required field"):
            MCPServer(registry, ExposureMap({"anime": ["search"]}))
