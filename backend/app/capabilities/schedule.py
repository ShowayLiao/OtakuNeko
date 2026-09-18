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
from app.schemas.schedule import (
    ScheduleCreate,
    ScheduleUpdate,
    ScheduleUpsert,
    ScheduleUpsertList,
)
from app.core.logging import get_logger

logger = get_logger(__name__)


def _public(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        try:
            dumped = value.model_dump(mode="json")
        except TypeError:
            dumped = value.model_dump()
        return _public(dumped)
    if isinstance(value, dict):
        return {key: _public(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_public(item) for item in value]
    return value

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
        actions = [
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
                        "watch_day": {"type": ["integer", "null"], "minimum": 0, "maximum": 6},
                        "watch_time": {"type": ["string", "null"]},
                        "duration": {"type": ["integer", "null"], "minimum": 0},
                        "watch_type": {"type": ["integer", "null"]},
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
                        "watch_day": {"type": ["integer", "null"], "minimum": 0, "maximum": 6},
                        "watch_time": {"type": ["string", "null"]},
                        "duration": {"type": ["integer", "null"], "minimum": 0},
                        "watch_type": {"type": ["integer", "null"]},
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

        actions.extend([
            ActionDescriptor(
                name="list_schedules_by_day",
                public_name="list_schedules_by_day",
                description="List the authenticated user's schedules for one weekday",
                input_schema={
                    "type": "object",
                    "properties": {"day_of_week": {"type": "integer", "minimum": 0, "maximum": 6}},
                    "required": ["day_of_week"],
                },
                requires_auth=True,
            ),
            ActionDescriptor(
                name="list_unified_schedules",
                public_name="list_unified_schedules",
                description="List schedules with their related subject and collection data",
                input_schema={"type": "object", "properties": {}, "required": []},
                requires_auth=True,
            ),
        ])

        write_common: dict[str, Any] = {
            "requires_auth": True,
            "is_side_effect": True,
            "idempotency_mode": "required",
            "risk_level": "medium",
        }
        schedule_item_schema = {
            "type": "object",
            "properties": {
                "id": {"type": ["integer", "null"]},
                "source": {"type": "string"},
                "source_id": {"type": "string"},
                "day_of_week": {"type": "integer", "minimum": 0, "maximum": 6},
                "start_time": {"type": "string"},
                "watch_day": {
                    "type": ["integer", "null"], "minimum": 0, "maximum": 6,
                },
                "watch_time": {"type": ["string", "null"]},
                "duration": {"type": ["integer", "null"], "minimum": 0},
                "watch_type": {"type": ["integer", "null"]},
            },
            "required": ["source", "source_id", "day_of_week", "start_time"],
            "additionalProperties": False,
        }
        actions.extend([
            ActionDescriptor(
                name="upsert_schedule",
                public_name="upsert_schedule",
                description="Create or update one schedule entry",
                input_schema={
                    "type": "object",
                    "properties": {
                        "id": {"type": ["integer", "null"]},
                        "source": {"type": "string"},
                        "source_id": {"type": "string"},
                        "day_of_week": {"type": "integer", "minimum": 0, "maximum": 6},
                        "start_time": {"type": "string"},
                        "watch_day": {"type": ["integer", "null"], "minimum": 0, "maximum": 6},
                        "watch_time": {"type": ["string", "null"]},
                        "duration": {"type": ["integer", "null"], "minimum": 0},
                        "watch_type": {"type": ["integer", "null"]},
                        "idempotency_key": {"type": "string"},
                    },
                    "required": ["source", "source_id", "day_of_week", "start_time"],
                },
                **write_common,
            ),
            ActionDescriptor(
                name="bulk_upsert_schedules",
                public_name="bulk_upsert_schedules",
                description="Create or update up to 100 schedule entries",
                input_schema={
                    "type": "object",
                    "properties": {
                        "items": {
                            "type": "array",
                            "items": schedule_item_schema,
                            "maxItems": 100,
                        },
                        "idempotency_key": {"type": "string"},
                    },
                    "required": ["items"],
                },
                max_payload_bytes=256 * 1024,
                **write_common,
            ),
            ActionDescriptor(
                name="sync_bangumi_schedule",
                public_name="sync_bangumi_schedule",
                description="Synchronize the authenticated user's schedule from Bangumi calendar data",
                input_schema={"type": "object", "properties": {"idempotency_key": {"type": "string"}}, "required": []},
                max_payload_bytes=16 * 1024,
                **write_common,
            ),
        ])
        return actions

    async def execute(self, action: str, **kwargs: Any) -> dict[str, Any]:
        handlers: dict[str, Any] = {
            "list_schedules": self._list,
            "create_schedule": self._create,
            "update_schedule": self._update,
            "delete_schedule": self._delete,
            "list_schedules_by_day": self._list_by_day,
            "list_unified_schedules": self._list_unified,
            "upsert_schedule": self._upsert,
            "bulk_upsert_schedules": self._bulk_upsert,
            "sync_bangumi_schedule": self._sync_bangumi,
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
            schedules=[_public(s) for s in schedules],
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
            watch_day=kwargs.get("watch_day"),
            watch_time=kwargs.get("watch_time"),
            duration=kwargs.get("duration"),
            watch_type=kwargs.get("watch_type"),
        )
        schedule = await ScheduleService.create_schedule(db, user_id, schedule_data)
        return CapabilityResult.ok(
            schedule=_public(schedule) if schedule is not None else None,
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

        update_data = {}
        for field in (
            "source", "source_id", "day_of_week", "start_time", "watch_day",
            "watch_time", "duration", "watch_type",
        ):
            if field in kwargs:
                update_data[field] = kwargs[field]

        schedule_update = ScheduleUpdate(**update_data)
        schedule = await ScheduleService.update_schedule(db, schedule_id, user_id, schedule_update)
        if schedule is None:
            return CapabilityResult.fail(
                "Schedule not found or access denied", error_type="not_found"
            ).to_dict()
        return CapabilityResult.ok(schedule=_public(schedule)).to_dict()

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

    async def _list_by_day(self, **kwargs: Any) -> dict[str, Any]:
        db = kwargs.get("db")
        if db is None:
            return CapabilityResult.fail("db session is required", error_type="invalid_args").to_dict()
        schedules = await ScheduleService.get_schedules_by_day(
            db, kwargs["user_id"], kwargs["day_of_week"]
        )
        return CapabilityResult.ok(
            schedules=[_public(item) for item in schedules], count=len(schedules)
        ).to_dict()

    async def _list_unified(self, **kwargs: Any) -> dict[str, Any]:
        db = kwargs.get("db")
        if db is None:
            return CapabilityResult.fail("db session is required", error_type="invalid_args").to_dict()
        result = await ScheduleService.get_unified_user_schedules(db, kwargs["user_id"])
        payload = _public(result)
        return CapabilityResult.ok(
            schedules=payload.get("items", []), count=payload.get("total", 0)
        ).to_dict()

    @staticmethod
    def _schedule_fields(kwargs: dict[str, Any]) -> dict[str, Any]:
        return {
            field: kwargs[field]
            for field in (
                "id", "source", "source_id", "day_of_week", "start_time", "watch_day",
                "watch_time", "duration", "watch_type",
            )
            if field in kwargs
        }

    async def _upsert(self, **kwargs: Any) -> dict[str, Any]:
        db = kwargs.get("db")
        if db is None:
            return CapabilityResult.fail("db session is required", error_type="invalid_args").to_dict()
        data = self._schedule_fields(kwargs)
        data["user_id"] = kwargs["user_id"]
        result = await ScheduleService.upsert_schedule(db, kwargs["user_id"], ScheduleUpsert(**data))
        if result is None:
            return CapabilityResult.fail("Schedule upsert failed", error_type="not_found").to_dict()
        return CapabilityResult.ok(
            schedule=_public(result), idempotency_key=kwargs.get("idempotency_key")
        ).to_dict()

    async def _bulk_upsert(self, **kwargs: Any) -> dict[str, Any]:
        db = kwargs.get("db")
        if db is None:
            return CapabilityResult.fail("db session is required", error_type="invalid_args").to_dict()
        raw_items = kwargs.get("items") or []
        if len(raw_items) > 100:
            return CapabilityResult.fail("At most 100 schedules may be written", error_type="invalid_args").to_dict()
        items = []
        for item in raw_items:
            data = self._schedule_fields(item)
            data["user_id"] = kwargs["user_id"]
            items.append(ScheduleUpsert(**data))
        result = await ScheduleService.bulk_upsert_schedules(
            db, kwargs["user_id"], ScheduleUpsertList(items=items)
        )
        return CapabilityResult.ok(
            schedules=[_public(item) for item in result], count=len(result),
            idempotency_key=kwargs.get("idempotency_key"),
        ).to_dict()

    async def _sync_bangumi(self, **kwargs: Any) -> dict[str, Any]:
        db = kwargs.get("db")
        if db is None:
            return CapabilityResult.fail("db session is required", error_type="invalid_args").to_dict()
        result = await ScheduleService.sync_bangumi_calendar(db, kwargs["user_id"])
        payload = _public(result)
        return CapabilityResult.ok(
            schedules=payload.get("items", []), count=payload.get("total", 0),
            idempotency_key=kwargs.get("idempotency_key"),
        ).to_dict()
