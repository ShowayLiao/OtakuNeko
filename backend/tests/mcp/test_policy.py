"""Policy and auth context tests for MCP-002."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import json
import pytest

from app.capabilities.anime import AnimeCapability
from app.capabilities.recommendation import RecommendationCapability
from app.capabilities.schedule import ScheduleCapability
from app.capabilities.registry import CapabilityRegistry
from app.mcp_server import MCPServer, ExposureMap
from app.mcp_server.context import MCPContext
from app.mcp_server.policy import Policy
from app.harness.policy import Approval, PolicyEngine, Principal


def _make_server() -> MCPServer:
    registry = CapabilityRegistry()
    registry.register(AnimeCapability())
    registry.register(RecommendationCapability())
    registry.register(ScheduleCapability())
    exposure = ExposureMap({
        "anime": ["search", "get_detail", "get_staff", "get_cast", "get_reviews"],
        "recommendation": ["generate_profile", "analyse_taste"],
        "schedule": ["create_schedule", "list_schedules"],
    })
    return MCPServer(registry, exposure)


class TestMCPContext:
    """MCPContext identity enforcement."""

    def test_anonymous_default(self):
        ctx = MCPContext()
        assert ctx.user_id is None
        assert ctx.is_authenticated is False

    def test_authenticated(self):
        ctx = MCPContext(user_id=42)
        assert ctx.user_id == 42
        assert ctx.is_authenticated is True


class TestPolicy:
    """Policy side-effect enforcement."""

    def test_default_denies_side_effects(self):
        p = Policy()
        assert p.allow_side_effects is False

    def test_explicit_allow(self):
        p = Policy(allow_side_effects=True, idempotency_key="create-1")
        assert p.allow_side_effects is True
        assert p.idempotency_key == "create-1"

    def test_harness_policy_defaults_to_deny_without_trusted_approval(self):
        descriptor = ScheduleCapability().actions()[1]
        decision = PolicyEngine().authorize(
            Principal(principal_id=1), descriptor, None, "key"
        )

        assert decision.allowed is False
        assert decision.error_type == "policy_denied"

    def test_harness_policy_requires_idempotency_after_approval(self):
        descriptor = ScheduleCapability().actions()[1]
        decision = PolicyEngine(allow_side_effects=True).authorize(
            Principal(principal_id=1),
            descriptor,
            Approval(approval_id="approval-1"),
            None,
        )

        assert decision.allowed is False
        assert decision.error_type == "idempotency_required"


class TestAuthAndPolicyIntegration:
    """Authentication and policy integration with MCPServer."""

    server = _make_server()

    @pytest.mark.asyncio
    async def test_anonymous_rejected(self):
        """Auth-required action without context is denied."""
        result = await self.server.call_tool(
            "recommendation_generate_profile", {"collections": []},
        )
        assert result["success"] is False
        assert result["error_type"] == "unauthorized"

    @pytest.mark.asyncio
    async def test_authenticated_applies_user_id(self, monkeypatch):
        """Authenticated context injects user_id and trusted dependencies."""
        captured = {}
        trusted_db = object()

        async def capture_execute(action_name, **kwargs):
            captured["user_id"] = kwargs.get("user_id")
            captured["db"] = kwargs.get("db")
            return {"success": True}

        monkeypatch.setattr(
            self.server._registry.get("recommendation"),
            "execute", capture_execute,
        )

        result = await self.server.call_tool(
            "recommendation_generate_profile",
            {"collections": []},
            context=MCPContext(user_id=99, extra={"db": trusted_db}),
        )
        assert result["success"] is True
        assert captured["user_id"] == 99
        assert captured["db"] is trusted_db

    @pytest.mark.asyncio
    async def test_cross_user_not_accepted_through_args(self):
        """user_id from untrusted tool args is not accepted as authority."""
        # Without context, user_id in args should not make it authenticated.
        result = await self.server.call_tool(
            "recommendation_generate_profile",
            {"user_id": 1, "collections": []},
        )
        # Still fails because requires_auth and no context.
        assert result["success"] is False
        assert result["error_type"] == "unauthorized"

    @pytest.mark.asyncio
    async def test_side_effect_denied_without_policy(self):
        """Side-effecting action without policy is denied."""
        result = await self.server.call_tool(
            "schedule_create_schedule",
            {"source": "bangumi", "source_id": "1",
             "day_of_week": 0, "start_time": "18:00:00"},
            context=MCPContext(user_id=1),
        )
        assert result["success"] is False
        assert result["error_type"] == "policy_denied"

    @pytest.mark.asyncio
    async def test_side_effect_with_policy_and_auth(self, monkeypatch):
        """Side-effecting action passes with both context and policy."""
        captured = {}

        async def capture_execute(action_name, **kwargs):
            captured["action"] = action_name
            return {"success": True, "data": "created"}

        monkeypatch.setattr(
            self.server._registry.get("schedule"),
            "execute", capture_execute,
        )

        result = await self.server.call_tool(
            "schedule_create_schedule",
            {"source": "bangumi", "source_id": "1",
             "day_of_week": 0, "start_time": "18:00:00"},
            context=MCPContext(user_id=1),
            policy=Policy(allow_side_effects=True, idempotency_key="create-1"),
        )
        assert result["success"] is True
        assert captured["action"] == "create_schedule"

    @pytest.mark.asyncio
    async def test_side_effect_requires_idempotency_key(self):
        result = await self.server.call_tool(
            "schedule_create_schedule",
            {"source": "bangumi", "source_id": "1",
             "day_of_week": 0, "start_time": "18:00:00"},
            context=MCPContext(user_id=1),
            policy=Policy(allow_side_effects=True),
        )

        assert result["success"] is False
        assert result["error_type"] == "idempotency_required"

    @pytest.mark.asyncio
    async def test_replayed_write_returns_cached_result(self, monkeypatch):
        calls = 0

        async def capture_execute(action_name, **kwargs):
            nonlocal calls
            calls += 1
            return {"success": True, "data": {"schedule_id": 7}}

        monkeypatch.setattr(
            self.server._registry.get("schedule"),
            "execute",
            capture_execute,
        )
        context = MCPContext(user_id=1, extra={"db": object()})
        policy = Policy(allow_side_effects=True, idempotency_key="create-7")
        arguments = {
            "source": "bangumi",
            "source_id": "1",
            "day_of_week": 0,
            "start_time": "18:00:00",
        }

        first = await self.server.call_tool(
            "schedule_create_schedule", arguments, context, policy
        )
        replay = await self.server.call_tool(
            "schedule_create_schedule", arguments, context, policy
        )

        assert replay == first
        assert calls == 1

    @pytest.mark.asyncio
    async def test_concurrent_replay_executes_write_once(self, monkeypatch):
        calls = 0
        release = asyncio.Event()

        async def capture_execute(action_name, **kwargs):
            nonlocal calls
            calls += 1
            await release.wait()
            return {"success": True, "data": {"schedule_id": 8}}

        monkeypatch.setattr(
            self.server._registry.get("schedule"), "execute", capture_execute
        )
        context = MCPContext(user_id=1)
        policy = Policy(allow_side_effects=True, idempotency_key="concurrent")
        arguments = {
            "source": "bangumi",
            "source_id": "1",
            "day_of_week": 0,
            "start_time": "18:00:00",
        }

        first = asyncio.create_task(
            self.server.call_tool(
                "schedule_create_schedule", arguments, context, policy
            )
        )
        await asyncio.sleep(0)
        replay = asyncio.create_task(
            self.server.call_tool(
                "schedule_create_schedule", arguments, context, policy
            )
        )
        await asyncio.sleep(0)
        release.set()

        assert await replay == await first
        assert calls == 1

    @pytest.mark.asyncio
    async def test_idempotency_key_rejects_different_payload(self, monkeypatch):
        async def capture_execute(action_name, **kwargs):
            return {"success": True}

        monkeypatch.setattr(
            self.server._registry.get("schedule"), "execute", capture_execute
        )
        context = MCPContext(user_id=1)
        policy = Policy(allow_side_effects=True, idempotency_key="conflict")
        base = {
            "source": "bangumi",
            "source_id": "1",
            "day_of_week": 0,
            "start_time": "18:00:00",
        }
        await self.server.call_tool(
            "schedule_create_schedule", base, context, policy
        )

        result = await self.server.call_tool(
            "schedule_create_schedule",
            {**base, "source_id": "2"},
            context,
            policy,
        )

        assert result["error_type"] == "idempotency_conflict"

    @pytest.mark.asyncio
    async def test_completed_idempotency_cache_is_bounded(self, monkeypatch):
        import app.mcp_server as module

        async def capture_execute(action_name, **kwargs):
            return {"success": True}

        monkeypatch.setattr(
            self.server._registry.get("schedule"), "execute", capture_execute
        )
        monkeypatch.setattr(module, "IDEMPOTENCY_CACHE_MAX_ENTRIES", 1)
        arguments = {
            "source": "bangumi",
            "source_id": "1",
            "day_of_week": 0,
            "start_time": "18:00:00",
        }
        for key in ("first", "second"):
            await self.server.call_tool(
                "schedule_create_schedule",
                arguments,
                MCPContext(user_id=1),
                Policy(allow_side_effects=True, idempotency_key=key),
            )

        assert len(self.server._completed_writes) == 1

    @pytest.mark.asyncio
    async def test_full_idempotency_cache_still_replays_existing_key(
        self, monkeypatch
    ):
        import app.mcp_server as module

        calls = 0

        async def capture_execute(action_name, **kwargs):
            nonlocal calls
            calls += 1
            return {"success": True}

        monkeypatch.setattr(
            self.server._registry.get("schedule"), "execute", capture_execute
        )
        monkeypatch.setattr(module, "IDEMPOTENCY_CACHE_MAX_ENTRIES", 1)
        arguments = {
            "source": "bangumi",
            "source_id": "1",
            "day_of_week": 0,
            "start_time": "18:00:00",
        }
        context = MCPContext(user_id=1)
        policy = Policy(allow_side_effects=True, idempotency_key="existing")

        await self.server.call_tool(
            "schedule_create_schedule", arguments, context, policy
        )
        await self.server.call_tool(
            "schedule_create_schedule", arguments, context, policy
        )

        assert calls == 1

    @pytest.mark.asyncio
    async def test_request_scoped_dependencies_are_not_shared(self, monkeypatch):
        databases = []
        both_started = asyncio.Event()

        @asynccontextmanager
        async def dependencies():
            database = object()
            yield {"db": database}

        async def capture_execute(action_name, **kwargs):
            databases.append(kwargs["db"])
            if len(databases) == 2:
                both_started.set()
            await both_started.wait()
            return {"success": True}

        monkeypatch.setattr(
            self.server._registry.get("schedule"), "execute", capture_execute
        )
        context = MCPContext(user_id=1, dependency_provider=dependencies)

        await asyncio.gather(
            self.server.call_tool("schedule_list_schedules", {}, context),
            self.server.call_tool("schedule_list_schedules", {}, context),
        )

        assert len(databases) == 2
        assert databases[0] is not databases[1]

    @pytest.mark.asyncio
    async def test_cancelled_write_releases_idempotency_key(self, monkeypatch):
        started = asyncio.Event()

        async def slow_execute(action_name, **kwargs):
            started.set()
            await asyncio.Event().wait()

        monkeypatch.setattr(
            self.server._registry.get("schedule"),
            "execute",
            slow_execute,
        )
        task = asyncio.create_task(self.server.call_tool(
            "schedule_create_schedule",
            {
                "source": "bangumi",
                "source_id": "1",
                "day_of_week": 0,
                "start_time": "18:00:00",
            },
            MCPContext(user_id=1),
            Policy(allow_side_effects=True, idempotency_key="cancelled-write"),
        ))
        await started.wait()

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert self.server._inflight_writes == {}

    @pytest.mark.asyncio
    async def test_json_serializable_error_has_type(self):
        """Denied responses are JSON serializable with error_type."""
        result = await self.server.call_tool(
            "recommendation_generate_profile", {"collections": []},
        )
        text = json.dumps(result, ensure_ascii=False)
        assert '"error_type"' in text
        assert '"unauthorized"' in text
