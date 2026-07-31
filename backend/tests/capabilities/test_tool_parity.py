"""Parity coverage for the legacy LangChain tool catalog."""

from __future__ import annotations

import pytest

from app.agents.tools import ALL_TOOLS
from app.capabilities.base import BaseCapability
from app.capabilities.factory import build_capability_registry
from app.capabilities.registry import CapabilityRegistry
from app.capabilities.types import ActionDescriptor
from app.harness.contracts import ExecutionContext


def _legacy_public_names() -> list[str]:
    return [tool.name for tool in ALL_TOOLS]


def test_every_legacy_tool_has_one_explicit_capability_action():
    registry = build_capability_registry()
    legacy_names = _legacy_public_names()

    assert len(legacy_names) == len(set(legacy_names))

    owners = []
    for public_name in legacy_names:
        owner = registry.find_action(public_name)
        assert owner is not None, f"Legacy tool '{public_name}' has no owning action"
        capability, descriptor = owner
        assert descriptor.public_name == public_name
        owners.append((capability.name, descriptor.name))

    assert len(owners) == len(set(owners))


def test_derived_tools_preserve_all_legacy_public_names():
    from app.capabilities.langchain_adapter import derive_tools

    derived_names = {
        tool.name for tool in derive_tools(build_capability_registry())
    }

    assert set(_legacy_public_names()) <= derived_names


def test_derived_tools_do_not_activate_side_effecting_actions():
    from app.capabilities.langchain_adapter import derive_tools

    derived_names = {
        tool.name for tool in derive_tools(build_capability_registry())
    }

    assert "create_schedule" not in derived_names
    assert "update_schedule" not in derived_names
    assert "delete_schedule" not in derived_names
    assert "add_rss_feed" not in derived_names


@pytest.mark.asyncio
async def test_derived_tool_strips_model_user_id_and_injects_trusted_context():
    calls: list[dict] = []

    class ProtectedCapability(BaseCapability):
        @property
        def name(self) -> str:
            return "protected"

        @property
        def description(self) -> str:
            return "protected reads"

        def actions(self) -> list[ActionDescriptor]:
            return [
                ActionDescriptor(
                    name="read_private",
                    public_name="read_private",
                    description="Read private data",
                    requires_auth=True,
                    input_schema={
                        "type": "object",
                        "properties": {
                            "user_id": {"type": "integer"},
                            "query": {"type": "string"},
                        },
                        "required": ["user_id", "query"],
                    },
                )
            ]

        async def execute(self, action: str, **kwargs):
            calls.append(kwargs)
            return {"success": True, "principal": kwargs["user_id"]}

    registry = CapabilityRegistry()
    registry.register(ProtectedCapability())
    from app.capabilities.langchain_adapter import derive_tools

    tools = derive_tools(
        registry,
        allowlist={"read_private"},
        context=ExecutionContext(
            principal_id=42,
            run_id="run-1",
            trace_id="trace-1",
        ),
    )

    result = await tools[0].ainvoke({"query": "q", "user_id": 999})

    assert result["principal"] == 42
    assert calls == [{"query": "q", "user_id": 42}]


class _PublicNameCapability(BaseCapability):
    def __init__(self, name: str, action: str, public_name: str) -> None:
        self._name = name
        self._action = action
        self._public_name = public_name

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return "test capability"

    def actions(self) -> list[ActionDescriptor]:
        return [
            ActionDescriptor(
                name=self._action,
                public_name=self._public_name,
                description="test action",
                input_schema={"type": "object", "properties": {}},
            )
        ]

    async def execute(self, action: str, **kwargs):
        return {"success": True}


def test_registry_rejects_duplicate_explicit_public_names():
    registry = CapabilityRegistry()
    registry.register(
        _PublicNameCapability("first", "first_action", "shared_public_name")
    )

    with pytest.raises(ValueError, match="shared_public_name"):
        registry.register(
            _PublicNameCapability("second", "second_action", "shared_public_name")
        )
