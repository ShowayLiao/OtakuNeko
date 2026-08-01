import pytest

from app.capabilities.schedule import ScheduleCapability
from app.harness.capability_adapter import CapabilityAdapter, CapabilityAgent
from app.harness.contracts import ExecutionContext
from app.harness.persistence.idempotency import InMemoryIdempotencyStore
from app.harness.policy import Approval, PolicyEngine
from app.harness.task import AgentTask


class FakeCapability:
    async def execute(self, action, **kwargs):
        assert action == "search"
        assert kwargs == {"keyword": "anime"}
        return {
            "success": True,
            "results": [{"id": 1, "name": "作品 A"}],
            "evidence": {"source": "catalog"},
        }


@pytest.mark.asyncio
async def test_capability_adapter_returns_generic_agent_result():
    agent = CapabilityAgent(
        name="anime.search",
        capability=FakeCapability(),
        action="search",
        input_builder=lambda task: {"keyword": task.goal},
    )

    result = await agent.execute(AgentTask(user_id=1, goal="anime"))

    assert result.kind == "capability"
    assert result.name == "anime.search"
    assert result.data["results"] == [{"id": 1, "name": "作品 A"}]
    assert result.evidence == {"source": "catalog"}


def _context(principal_id: int) -> ExecutionContext:
    return ExecutionContext(
        principal_id=principal_id,
        run_id=f"run-{principal_id}",
        trace_id=f"trace-{principal_id}",
    )


class _FakeSchedule:
    def __init__(self, schedule_id: int, user_id: int) -> None:
        self.schedule_id = schedule_id
        self.user_id = user_id

    def model_dump(self) -> dict[str, int]:
        return {"id": self.schedule_id, "user_id": self.user_id}


@pytest.fixture
def schedule_adapter(monkeypatch):
    calls: list[int] = []
    next_id = 0

    async def create_schedule(db, user_id, schedule_data):
        nonlocal next_id
        next_id += 1
        calls.append(user_id)
        return _FakeSchedule(next_id, user_id)

    from app.services.schedule_service import ScheduleService

    monkeypatch.setattr(ScheduleService, "create_schedule", create_schedule)
    adapter = CapabilityAdapter(
        ScheduleCapability(),
        policy_engine=PolicyEngine(allow_side_effects=True),
        approval=Approval(approval_id="approval-1"),
        idempotency_store=InMemoryIdempotencyStore(),
        trusted_args={"db": object()},
    )
    return adapter, calls


def _create_args(key: str, source_id: str = "1") -> dict[str, object]:
    return {
        "source": "bangumi",
        "source_id": source_id,
        "day_of_week": 0,
        "start_time": "18:00:00",
        "idempotency_key": key,
    }


@pytest.mark.asyncio
async def test_context_principal_is_injected_and_replay_uses_idempotency_port(
    schedule_adapter,
):
    adapter, calls = schedule_adapter

    first = await adapter.execute(_context(7), "create_schedule", _create_args("same"))
    replay = await adapter.execute(_context(7), "create_schedule", _create_args("same"))

    assert first["success"] is True
    assert replay == first
    assert calls == [7]


@pytest.mark.asyncio
async def test_idempotency_scope_separates_authenticated_principals(schedule_adapter):
    adapter, calls = schedule_adapter

    first = await adapter.execute(_context(7), "create_schedule", _create_args("same"))
    second = await adapter.execute(_context(8), "create_schedule", _create_args("same"))

    assert first["success"] is True
    assert second["success"] is True
    assert calls == [7, 8]


@pytest.mark.asyncio
async def test_changed_payload_with_same_key_is_conflict(schedule_adapter):
    adapter, calls = schedule_adapter

    await adapter.execute(_context(7), "create_schedule", _create_args("same", "1"))
    result = await adapter.execute(_context(7), "create_schedule", _create_args("same", "2"))

    assert result["success"] is False
    assert result["error_type"] == "idempotency_conflict"
    assert calls == [7]


@pytest.mark.asyncio
async def test_write_without_approval_or_key_never_calls_service(monkeypatch):
    calls = 0

    async def create_schedule(*args, **kwargs):
        nonlocal calls
        calls += 1

    from app.services.schedule_service import ScheduleService

    monkeypatch.setattr(ScheduleService, "create_schedule", create_schedule)
    adapter = CapabilityAdapter(
        ScheduleCapability(),
        idempotency_store=InMemoryIdempotencyStore(),
        trusted_args={"db": object()},
    )
    denied = await adapter.execute(_context(7), "create_schedule", _create_args("key"))

    approved_adapter = CapabilityAdapter(
        ScheduleCapability(),
        policy_engine=PolicyEngine(allow_side_effects=True),
        approval=Approval(approval_id="approval-1"),
        idempotency_store=InMemoryIdempotencyStore(),
        trusted_args={"db": object()},
    )
    missing_key = await approved_adapter.execute(
        _context(7), "create_schedule", _create_args("")
    )

    assert denied["error_type"] == "policy_denied"
    assert missing_key["error_type"] == "idempotency_required"
    assert calls == 0


@pytest.mark.asyncio
async def test_model_cannot_override_authenticated_principal(schedule_adapter):
    adapter, calls = schedule_adapter

    result = await adapter.execute(
        _context(7),
        "create_schedule",
        {**_create_args("key"), "user_id": 999},
    )

    assert result["success"] is False
    assert result["error_type"] == "identity_spoofing"
    assert calls == []


@pytest.mark.asyncio
async def test_authenticated_schedule_read_uses_only_context_principal(monkeypatch):
    calls: list[int] = []

    async def get_user_schedules(db, user_id):
        calls.append(user_id)
        return []

    from app.services.schedule_service import ScheduleService

    monkeypatch.setattr(ScheduleService, "get_user_schedules", get_user_schedules)
    adapter = CapabilityAdapter(
        ScheduleCapability(),
        trusted_args={"db": object()},
    )

    result = await adapter.execute(_context(13), "list_schedules", {})
    denied = await adapter.execute(None, "list_schedules", {})

    assert result["success"] is True
    assert calls == [13]
    assert denied["error_type"] == "unauthorized"
