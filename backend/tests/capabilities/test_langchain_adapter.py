"""Tests for CAPABILITY-003 Step 02: LangChain adapter and shared factory."""

from __future__ import annotations

from app.capabilities.anime import AnimeCapability
from app.capabilities.factory import build_capability_registry
from app.capabilities.langchain_adapter import (
    _build_runtime_tool,
    derive_tools,
)
from app.capabilities.schedule import ScheduleCapability


class TestLangChainAdapter:
    def test_build_tool_has_correct_metadata(self):
        cap = AnimeCapability()
        descriptor = next(a for a in cap.actions() if a.name == "search")
        tool = _build_runtime_tool(cap, descriptor)

        assert tool.name == "search_anime_advanced"
        assert tool.description == descriptor.description
        assert "keyword" in tool.args if hasattr(tool, "args") else True

    def test_derive_tools_returns_all_actions(self):
        registry = build_capability_registry()
        tools = derive_tools(registry)

        assert len(tools) > 0
        names = {t.name for t in tools}
        assert "search_anime_advanced" in names
        assert "get_anime_info" in names
        assert "generate_user_profile_tool" in names

    def test_schedule_public_tool_schema_has_no_user_id(self):
        capability = ScheduleCapability()
        descriptor = next(
            action for action in capability.actions() if action.name == "create_schedule"
        )
        tool = _build_runtime_tool(capability, descriptor)

        assert "user_id" not in tool.args
        assert "principal_id" not in tool.args
        assert "idempotency_key" in tool.args


class TestSharedFactory:
    def test_factory_registers_all_capabilities(self):
        registry = build_capability_registry()
        names = registry.list_names()

        assert "anime" in names
        assert "recommendation" in names
        assert "schedule" in names
        assert "media" in names
        assert "system" in names

    def test_factory_action_inventory(self):
        registry = build_capability_registry()
        actions = registry.list_actions()
        action_names = {a.name for a in actions}

        assert "search" in action_names
        assert "get_detail" in action_names
        assert "get_staff" in action_names
        assert "get_cast" in action_names
        assert "get_reviews" in action_names
        assert "generate_profile" in action_names
        assert "analyse_taste" in action_names
        assert "list_schedules" in action_names
        assert "library_status" in action_names
        assert "current_time" in action_names

    def test_factory_registry_has_stable_order(self):
        r1 = build_capability_registry()
        r2 = build_capability_registry()
        assert r1.list_names() == r2.list_names()
