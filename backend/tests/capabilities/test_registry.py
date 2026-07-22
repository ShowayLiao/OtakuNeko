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
