"""Tests for CAPABILITY-002: ScheduleCapability."""

import pytest

from app.capabilities.schedule import ScheduleCapability, _idempotency_key
from app.harness.normalizer import SchemaContractError, validate_input


@pytest.fixture
def capability():
    return ScheduleCapability()


class TestScheduleCapability:
    def test_name_is_schedule(self, capability):
        assert capability.name == "schedule"

    def test_actions_declare_side_effects(self, capability):
        actions = {a.name: a for a in capability.actions()}
        assert actions["list_schedules"].is_side_effect is False
        assert actions["list_schedules_by_day"].is_side_effect is False
        assert actions["list_unified_schedules"].is_side_effect is False
        assert actions["create_schedule"].is_side_effect is True
        assert actions["update_schedule"].is_side_effect is True
        assert actions["delete_schedule"].is_side_effect is True
        assert actions["upsert_schedule"].is_side_effect is True
        assert actions["bulk_upsert_schedules"].is_side_effect is True
        assert actions["sync_bangumi_schedule"].is_side_effect is True

    def test_write_actions_require_auth(self, capability):
        actions = {a.name: a for a in capability.actions()}
        for name in (
            "create_schedule",
            "update_schedule",
            "delete_schedule",
            "upsert_schedule",
            "bulk_upsert_schedules",
            "sync_bangumi_schedule",
        ):
            assert actions[name].requires_auth is True, f"{name} must require auth"

    def test_public_schema_does_not_expose_authority_fields(self, capability):
        actions = {a.name: a for a in capability.actions()}
        for action in actions.values():
            properties = action.input_schema.get("properties", {})
            required = action.input_schema.get("required", [])
            assert "user_id" not in properties
            assert "principal_id" not in properties
            assert "user_id" not in required
            assert "principal_id" not in required

        for name in ("create_schedule", "update_schedule", "delete_schedule"):
            descriptor = actions[name]
            assert descriptor.idempotency_mode == "required"
            assert "idempotency_key" in descriptor.input_schema["properties"]

    def test_bulk_schema_validates_each_schedule_item(self, capability):
        action = next(
            action
            for action in capability.actions()
            if action.name == "bulk_upsert_schedules"
        )

        validate_input(
            {
                "items": [
                    {
                        "source": "bangumi",
                        "source_id": "1",
                        "day_of_week": 1,
                        "start_time": "20:00:00",
                    }
                ],
            },
            action,
        )
        with pytest.raises(SchemaContractError):
            validate_input({"items": ["not a schedule"]}, action)

    @pytest.mark.asyncio
    async def test_missing_user_id_returns_unauthorized(self, capability):
        for action in (
            "create_schedule",
            "update_schedule",
            "delete_schedule",
            "list_schedules",
            "list_schedules_by_day",
            "list_unified_schedules",
        ):
            result = await capability.execute(action)
            assert result["success"] is False, f"{action} should reject missing user_id"
            assert result.get("error_type") == "unauthorized"

    @pytest.mark.asyncio
    async def test_missing_db_for_list_returns_invalid_args(self, capability):
        result = await capability.execute("list_schedules", user_id=1)
        assert result["success"] is False
        assert result.get("error_type") == "invalid_args"

    @pytest.mark.asyncio
    async def test_unknown_action_returns_error(self, capability):
        result = await capability.execute("bogus", user_id=1)
        assert result["success"] is False


class TestIdempotency:
    def test_same_payload_produces_same_key(self):
        a = _idempotency_key(1, "create_schedule", {"source": "b", "source_id": "1"})
        b = _idempotency_key(1, "create_schedule", {"source": "b", "source_id": "1"})
        assert a == b

    def test_different_user_produces_different_key(self):
        a = _idempotency_key(1, "create_schedule", {"x": "y"})
        b = _idempotency_key(2, "create_schedule", {"x": "y"})
        assert a != b

    def test_different_action_produces_different_key(self):
        a = _idempotency_key(1, "create_schedule", {})
        b = _idempotency_key(1, "update_schedule", {})
        assert a != b

    def test_runtime_objects_do_not_change_key(self):
        a = _idempotency_key(
            1,
            "create_schedule",
            {"source": "b", "source_id": "1", "db": object()},
        )
        b = _idempotency_key(
            1,
            "create_schedule",
            {"source": "b", "source_id": "1", "db": object()},
        )
        assert a == b
