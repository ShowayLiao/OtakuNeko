import pytest

from app.capabilities.base import BaseCapability
from app.capabilities.registry import CapabilityRegistry
from app.capabilities.types import ActionDescriptor


class StubCapability(BaseCapability):
    @property
    def name(self) -> str:
        return "stub"

    @property
    def description(self) -> str:
        return "stub capability"

    def actions(self) -> list[ActionDescriptor]:
        return [
            ActionDescriptor(
                name="do_stuff",
                description="Stub action",
                input_schema={"type": "object", "properties": {}},
            )
        ]

    async def execute(self, action: str, **kwargs):
        return {"action": action, **kwargs}


class AnotherStubCapability(BaseCapability):
    """A second stub whose action name conflicts with StubCapability."""

    @property
    def name(self) -> str:
        return "another_stub"

    @property
    def description(self) -> str:
        return "another stub capability"

    def actions(self) -> list[ActionDescriptor]:
        return [
            ActionDescriptor(
                name="do_stuff",
                description="Same action name as StubCapability",
                input_schema={"type": "object", "properties": {}},
            )
        ]

    async def execute(self, action: str, **kwargs):
        return {"action": action, **kwargs}


class WriteStubCapability(BaseCapability):
    @property
    def name(self) -> str:
        return "writer"

    @property
    def description(self) -> str:
        return "write capability"

    def actions(self) -> list[ActionDescriptor]:
        return [
            ActionDescriptor(
                name="write_data",
                public_name="write_data",
                description="Write data",
                input_schema={"type": "object", "properties": {"user_id": {"type": "integer"}}},
                is_side_effect=True,
            )
        ]

    async def execute(self, action: str, **kwargs):
        return {"success": True}


def test_registry_register_lookup_and_unregister():
    registry = CapabilityRegistry()
    capability = StubCapability()

    registry.register(capability)

    assert registry.get("stub") is capability
    assert registry.list_names() == ["stub"]
    registry.unregister("stub")
    with pytest.raises(KeyError):
        registry.get("stub")


def test_registry_rejects_duplicate_names():
    registry = CapabilityRegistry()
    registry.register(StubCapability())

    with pytest.raises(ValueError, match="already registered"):
        registry.register(StubCapability())


def test_registry_rejects_duplicate_action_names():
    registry = CapabilityRegistry()
    registry.register(StubCapability())

    with pytest.raises(ValueError, match="conflicts"):
        registry.register(AnotherStubCapability())


def test_list_actions_returns_all_actions():
    registry = CapabilityRegistry()
    registry.register(StubCapability())

    actions = registry.list_actions()
    assert len(actions) == 1
    assert actions[0].name == "do_stuff"


def test_registry_returns_versioned_public_definition_without_authority_fields():
    registry = CapabilityRegistry()
    registry.register(StubCapability())

    definition = registry.get_public_definition("do_stuff", "v1")

    assert definition is not None
    assert definition.name == "do_stuff"
    assert definition.version == "v1"
    assert "user_id" not in definition.input_schema.get("properties", {})
    assert "user_id" not in definition.to_dict()
    assert "capability_object" not in definition.to_dict()
    assert registry.get_public_definition("do_stuff", "v2") is None


def test_registry_default_public_allowlist_excludes_writes():
    registry = CapabilityRegistry()
    registry.register(StubCapability())
    registry.register(WriteStubCapability())

    definitions = registry.allowed_public_definitions()
    explicit = registry.allowed_public_definitions({"do_stuff", "write_data"})

    assert [definition.public_name for definition in definitions] == ["do_stuff"]
    assert [definition.public_name for definition in explicit] == ["do_stuff"]
    write = registry.get_public_definition("write_data", "v1")
    assert write is not None
    assert write.approval_required is True


def test_registry_can_explicitly_discover_side_effects_for_authenticated_runs():
    registry = CapabilityRegistry()
    registry.register(StubCapability())
    registry.register(WriteStubCapability())

    definitions = registry.allowed_public_definitions(include_side_effects=True)

    assert [definition.public_name for definition in definitions] == [
        "do_stuff",
        "write_data",
    ]
    write = definitions[-1]
    assert write.is_side_effect is True
    assert write.approval_required is True


def test_production_registry_includes_service_backed_data_capabilities():
    from app.capabilities.factory import build_capability_registry

    registry = build_capability_registry()

    assert set(registry.list_names()) >= {
        "collections",
        "subjects",
        "stats",
    }


def test_registry_validates_public_output_with_schema_and_size_limit():
    registry = CapabilityRegistry()
    registry.register(StubCapability())

    valid = registry.validate_public_output(
        "do_stuff", {"value": "ok"}, output_schema={"type": "object", "required": ["value"]}
    )
    invalid = registry.validate_public_output(
        "do_stuff", {"other": "ok"}, output_schema={"type": "object", "required": ["value"]}
    )
    oversized = registry.validate_public_output("do_stuff", {"value": "x"}, max_payload_bytes=1)

    assert valid == {"success": True, "data": {"value": "ok"}}
    assert invalid["error_type"] == "invalid_output"
    assert oversized["error_type"] == "payload_too_large"
