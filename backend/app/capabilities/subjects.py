"""Subject/catalog capability backed by the existing subject services."""

from __future__ import annotations

from typing import Any

from app.capabilities.base import BaseCapability
from app.capabilities.types import ActionDescriptor, CapabilityResult
from app.core.logging import get_logger
from app.schemas.subject import (
    SubjectSearchBase,
    SubjectSearchByID,
    SubjectSearchByName,
    SubjectSearchCloud,
)
from app.services.subject_service import (
    get_subject_by_source,
    search_mixed,
    search_subject_by_name,
    search_subject_cloud,
)


logger = get_logger(__name__)


def _schema(
    properties: dict[str, Any], required: list[str] | None = None
) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required or []}


def _public(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return _public(value.model_dump(mode="json"))
    if isinstance(value, dict):
        return {key: _public(item) for key, item in value.items() if key != "user_id"}
    if isinstance(value, list):
        return [_public(item) for item in value]
    return value


class SubjectCapability(BaseCapability):
    @property
    def name(self) -> str:
        return "subjects"

    @property
    def description(self) -> str:
        return "Search local, remote, and mixed subject catalog data for the authenticated user"

    def actions(self) -> list[ActionDescriptor]:
        reference = _schema(
            {
                "source": {"type": "string"},
                "source_id": {"type": "string", "minLength": 1},
            },
            ["source", "source_id"],
        )
        search = {
            "keyword": {"type": "string"},
            "type": {"type": "integer"},
            "skip": {"type": "integer", "minimum": 0},
            "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            "sort_by": {"type": "string"},
        }
        return [
            ActionDescriptor(
                "get_subject",
                "Get one local subject and its owned collection",
                reference,
                requires_auth=True,
                public_name="get_subject",
            ),
            ActionDescriptor(
                "search_local_subjects",
                "Search local subjects and owned collection metadata",
                _schema(search),
                requires_auth=True,
                public_name="search_local_subjects",
            ),
            ActionDescriptor(
                "search_remote_subjects",
                "Search the remote Bangumi subject catalog",
                _schema(search),
                public_name="search_remote_subjects",
            ),
            ActionDescriptor(
                "search_mixed_subjects",
                "Search local and remote subjects and merge results",
                _schema(search),
                requires_auth=True,
                public_name="search_mixed_subjects",
            ),
            ActionDescriptor(
                "get_subject_air_time",
                "Read the locally synchronized air time for a subject",
                reference,
                requires_auth=True,
                public_name="get_subject_air_time",
            ),
        ]

    async def execute(self, action: str, **kwargs: Any) -> dict[str, Any]:
        handler = {
            "get_subject": self._get,
            "search_local_subjects": self._local,
            "search_remote_subjects": self._remote,
            "search_mixed_subjects": self._mixed,
            "get_subject_air_time": self._air_time,
        }.get(action)
        if handler is None:
            return CapabilityResult.fail(
                f"Unknown action: {action}", error_type="invalid_action"
            ).to_dict()
        try:
            return await handler(**kwargs)
        except ValueError as exc:
            return CapabilityResult.fail(str(exc), error_type="invalid_args").to_dict()
        except Exception:
            logger.exception("subject_capability_failed", extra={"action": action})
            return CapabilityResult.fail(
                "Subject operation failed", error_type="internal"
            ).to_dict()

    @staticmethod
    def _require_db(
        kwargs: dict[str, Any], *, auth: bool
    ) -> tuple[Any, int | None] | None:
        db = kwargs.get("db")
        user_id = kwargs.get("user_id")
        if db is None or (auth and (not isinstance(user_id, int) or user_id <= 0)):
            return None
        return db, user_id

    async def _get(self, **kwargs: Any) -> dict[str, Any]:
        trusted = self._require_db(kwargs, auth=True)
        if trusted is None:
            return CapabilityResult.fail(
                "Trusted db and principal are required", error_type="invalid_args"
            ).to_dict()
        db, user_id = trusted
        result = await get_subject_by_source(
            db,
            SubjectSearchByID(
                source=kwargs["source"],
                source_id=str(kwargs["source_id"]),
                user_id=user_id,
            ),
        )
        if result is None:
            return CapabilityResult.fail(
                "Subject not found", error_type="not_found"
            ).to_dict()
        return CapabilityResult.ok(subject=_public(result)).to_dict()

    async def _local(self, **kwargs: Any) -> dict[str, Any]:
        trusted = self._require_db(kwargs, auth=True)
        if trusted is None:
            return CapabilityResult.fail(
                "Trusted db and principal are required", error_type="invalid_args"
            ).to_dict()
        db, user_id = trusted
        result = await search_subject_by_name(
            db,
            SubjectSearchByName(
                keyword=kwargs.get("keyword", ""),
                type=kwargs.get("type"),
                skip=kwargs.get("skip", 0),
                limit=min(kwargs.get("limit", 10), 100),
                user_id=user_id,
                sort_by=kwargs.get("sort_by", "updated_at"),
            ),
        )
        payload = _public(result)
        return CapabilityResult.ok(
            total=payload.get("total", 0), subjects=payload.get("items", [])
        ).to_dict()

    async def _remote(self, **kwargs: Any) -> dict[str, Any]:
        result = await search_subject_cloud(
            None,
            SubjectSearchCloud(
                keyword=kwargs.get("keyword", ""),
                type=kwargs.get("type"),
                skip=kwargs.get("skip", 0),
                limit=min(kwargs.get("limit", 10), 100),
                user_id=None,
            ),
        )
        payload = _public(result)
        return CapabilityResult.ok(
            total=payload.get("total", 0), subjects=payload.get("items", [])
        ).to_dict()

    async def _mixed(self, **kwargs: Any) -> dict[str, Any]:
        trusted = self._require_db(kwargs, auth=True)
        if trusted is None:
            return CapabilityResult.fail(
                "Trusted db and principal are required", error_type="invalid_args"
            ).to_dict()
        db, user_id = trusted
        result = await search_mixed(
            db,
            SubjectSearchBase(
                keyword=kwargs.get("keyword"),
                type=kwargs.get("type"),
                skip=kwargs.get("skip", 0),
                limit=min(kwargs.get("limit", 10), 100),
                user_id=user_id,
                sort_by=kwargs.get("sort_by", "updated_at"),
            ),
        )
        payload = _public(result)
        return CapabilityResult.ok(
            total=payload.get("total", 0), subjects=payload.get("items", [])
        ).to_dict()

    async def _air_time(self, **kwargs: Any) -> dict[str, Any]:
        result = await self._get(**kwargs)
        if not result.get("success"):
            return result
        subject = result.get("subject") or {}
        subject_data = subject.get("subject") if isinstance(subject, dict) else {}
        return CapabilityResult.ok(
            source=kwargs["source"],
            source_id=str(kwargs["source_id"]),
            air_time=(subject_data or {}).get("air_time"),
            air_weekday=(subject_data or {}).get("air_weekday"),
        ).to_dict()
