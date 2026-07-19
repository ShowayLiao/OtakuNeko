import pytest

from app.capabilities.base import BaseCapability
from app.capabilities.registry import CapabilityRegistry


class StubCapability(BaseCapability):
    @property
    def name(self) -> str:
        return "stub"

    @property
    def description(self) -> str:
        return "stub capability"

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
