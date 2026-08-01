"""Schedule capability — wraps the existing schedule service.

Write actions declare side effects, validate ownership, and use
idempotency keys where duplicate execution could create duplicates.
"""

from __future__ import annotations

from hashlib import sha256
import json
from typing import Any

from app.capabilities.base import BaseCapability
from app.capabilities.types import ActionDescriptor, CapabilityResult
from app.services.schedule_service import ScheduleService
from app.schemas.schedule import ScheduleCreate
from app.core.logging import get_logger

logger = get_logger(__name__)

def _idempotency_key(user_id: int, action: str, payload: dict[str, Any]) -> str:
    """Derive a stable idempotency key from (user, action, payload)."""
    business_payload = {
        key: value
        for key, value in payload.items()
        if key not in {"db", "idempotency_key"}
    }
    raw_payload = json.dumps(business_payload, sort_keys=True, default=str)
    raw = f"{user_id}:{action}:{raw_payload}"
    return sha256(raw.encode()).hexdigest()[:12]


class ScheduleCapability(BaseCapability):
    """Read and write user schedule records.

    The public action contract contains no authority fields. Runtime adapters
    inject the authenticated user ID before reusing the domain service.
    """

    @property
    def name(self) -> str:
        return "schedule"

    @property
    def description(self) -> str:
        return "List, create, update, and delete user viewing schedules"

    def actions(self) -> list[ActionDescriptor]:
        return [
            ActionDescriptor(
                name="list_schedules",
                public_name="list_schedules",
                description="List all schedules for a user",
                input_schema={
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
                requires_auth=True,
            ),
            ActionDescriptor(
                name="create_schedule",
                public_name="create_schedule",
                description="Create a new schedule entry",
                input_schema={
                    "type": "object",
                    "properties": {
                        "source": {"type": "string", "description": "Data source (bangumi/douban)"},
                        "source_id": {
                            "type": "string", "description": "ID from the source system",
                        },
                        "day_of_week": {
                            "type": "integer", "minimum": 0, "maximum": 6,
                            "description": "Day of week (0=Sun, 6=Sat)",
                        },
                        "start_time": {
                            "type": "string", "description": "Broadcast time (HH:MM:SS)",
                        },
                        "idempotency_key": {
                            "type": "string",
                            "description": "Client-generated idempotency key",
                        },
                    },
                    "required": [
                        "source", "source_id", "day_of_week", "start_time",
                    ],
                },
                requires_auth=True,
                is_side_effect=True,
                idempotency_mode="required",
            ),
            ActionDescriptor(
                name="update_schedule",
                public_name="update_schedule",
                description="Update an existing schedule entry",
                input_schema={
                    "type": "object",
                    "properties": {
                        "schedule_id": {"type": "integer", "description": "Schedule record ID"},
                        "day_of_week": {"type": "integer", "minimum": 0, "maximum": 6},
                        "start_time": {"type": "string", "description": "Broadcast time (HH:MM:SS)"},
                        "idempotency_key": {
                            "type": "string",
                            "description": "Client-generated idempotency key",
                        },
                    },
                    "required": ["schedule_id"],
                },
                requires_auth=True,
                is_side_effect=True,
                idempotency_mode="required",
            ),
            ActionDescriptor(
                name="delete_schedule",
                public_name="delete_schedule",
                description="Delete a schedule entry",
                input_schema={
                    "type": "object",
                    "properties": {
                        "schedule_id": {"type": "integer", "description": "Schedule record ID"},
                        "idempotency_key": {
                            "type": "string",
                            "description": "Client-generated idempotency key",
                        },
                    },
                    "required": ["schedule_id"],
                },
                requires_auth=True,
                is_side_effect=True,
                idempotency_mode="required",
            ),
        ]

    async def execute(self, action: str, **kwargs: Any) -> dict[str, Any]:
        handlers: dict[str, Any] = {
            "list_schedules": self._list,
            "create_schedule": self._create,
            "update_schedule": self._update,
            "delete_schedule": self._delete,
        }
        handler = handlers.get(action)
        if handler is None:
            return CapabilityResult.fail(
                f"Unknown action: {action}", error_type="invalid_action"
            ).to_dict()

        user_id = kwargs.get("user_id")
        if user_id is None:
            return CapabilityResult.fail(
                "user_id is required", error_type="unauthorized"
            ).to_dict()

        try:
            return await handler(**kwargs)
        except Exception as exc:
            logger.error(
                "schedule_capability_failed",
                extra={"action": action, "error_type": type(exc).__name__},
            )
            return CapabilityResult.fail(
                "Schedule operation failed", error_type="internal"
            ).to_dict()

    async def _list(self, **kwargs: Any) -> dict[str, Any]:
        user_id: int = kwargs["user_id"]
        db = kwargs.get("db")
        if db is None:
            return CapabilityResult.fail(
                "db session is required", error_type="invalid_args"
            ).to_dict()

        schedules = await ScheduleService.get_user_schedules(db, user_id)
        return CapabilityResult.ok(
            schedules=[s.model_dump() for s in schedules],
            count=len(schedules),
        ).to_dict()

    async def _create(self, **kwargs: Any) -> dict[str, Any]:
        user_id: int = kwargs["user_id"]
        db = kwargs.get("db")
        if db is None:
            return CapabilityResult.fail(
                "db session is required", error_type="invalid_args"
            ).to_dict()

        idempotency_key = kwargs.get("idempotency_key")
        schedule_data = ScheduleCreate(
            source=kwargs["source"],
            source_id=str(kwargs["source_id"]),
            day_of_week=kwargs["day_of_week"],
            start_time=kwargs["start_time"],
            user_id=user_id,
        )
        schedule = await ScheduleService.create_schedule(db, user_id, schedule_data)
        return CapabilityResult.ok(
            schedule=schedule.model_dump() if schedule is not None else None,
            idempotency_key=idempotency_key,
        ).to_dict()

    async def _update(self, **kwargs: Any) -> dict[str, Any]:
        user_id: int = kwargs["user_id"]
        schedule_id: int = kwargs["schedule_id"]
        db = kwargs.get("db")
        if db is None:
            return CapabilityResult.fail(
                "db session is required", error_type="invalid_args"
            ).to_dict()

        from app.schemas.schedule import ScheduleUpdate

        update_data = {}
        if "day_of_week" in kwargs:
            update_data["day_of_week"] = kwargs["day_of_week"]
        if "start_time" in kwargs:
            update_data["start_time"] = kwargs["start_time"]

        schedule_update = ScheduleUpdate(**update_data)
        schedule = await ScheduleService.update_schedule(db, schedule_id, user_id, schedule_update)
        if schedule is None:
            return CapabilityResult.fail(
                "Schedule not found or access denied", error_type="not_found"
            ).to_dict()
        return CapabilityResult.ok(schedule=schedule.model_dump()).to_dict()

    async def _delete(self, **kwargs: Any) -> dict[str, Any]:
        user_id: int = kwargs["user_id"]
        schedule_id: int = kwargs["schedule_id"]
        db = kwargs.get("db")
        if db is None:
            return CapabilityResult.fail(
                "db session is required", error_type="invalid_args"
            ).to_dict()

        deleted = await ScheduleService.delete_schedule(db, schedule_id, user_id)
        if not deleted:
            return CapabilityResult.fail(
                "Schedule not found or access denied", error_type="not_found"
            ).to_dict()
        return CapabilityResult.ok(deleted=True).to_dict()
