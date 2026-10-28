"""Current-user collection capability.

The domain services already enforce the collection business rules. This
boundary is responsible for keeping identity and database dependencies out of
the model contract while exposing bounded read/write operations to Runtime.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

from app.capabilities.base import BaseCapability
from app.capabilities.collections_read_contracts import output_schema
from app.capabilities.collections_write_contracts import (
    WRITE_ACTIONS,
    output_schema as write_output_schema,
)
from app.capabilities.types import ActionDescriptor, CapabilityResult
from app.core.logging import get_logger
from app.schemas.collection import (
    CollectionCreate,
    CollectionSearchBase,
    CollectionSearchByID,
    CollectionSearchByName,
    CollectionUpdate,
    CollectionUpsert,
    CollectionUpsertList,
    CollectionUpsertRequest,
)
from app.services.bangumi_service import sync_user_collections
from app.services.collection_service import (
    batch_upsert_collections,
    create_collection,
    delete_collection,
    get_collection,
    get_user_collections,
    import_json_collections,
    search_collections,
    update_collection,
    upsert_collection,
)
from app.services.douban_service import sync_user_collections_douban


logger = get_logger(__name__)


_COLLECTION_FIELDS: dict[str, Any] = {
    "source": {"type": "string", "enum": ["bangumi", "douban"]},
    "source_id": {"type": "string", "minLength": 1, "maxLength": 50},
    "type": {"type": "integer", "minimum": 1, "maximum": 5},
    "rate": {"type": ["integer", "null"], "minimum": 0, "maximum": 10},
    "comment": {"type": ["string", "null"], "maxLength": 500},
    "private": {"type": "boolean"},
    "tags": {"type": ["array", "null"], "items": {"type": "string"}},
    "vol_status": {"type": "integer"},
    "ep_status": {"type": "integer"},
    "subject_type": {"type": "integer"},
}


def _schema(
    properties: dict[str, Any], required: list[str] | None = None
) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
        "additionalProperties": False,
    }


def _public(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return _public(value.model_dump(mode="json"))
    if isinstance(value, dict):
        return {key: _public(item) for key, item in value.items() if key != "user_id"}
    if isinstance(value, list):
        return [_public(item) for item in value]
    return value


def _read_schema(
    properties: dict[str, Any], required: list[str] | None = None
) -> dict[str, Any]:
    return {**_schema(properties, required), "additionalProperties": False}


def _trusted(kwargs: dict[str, Any]) -> tuple[Any, int] | None:
    db = kwargs.get("db")
    user_id = kwargs.get("user_id")
    if db is None or not isinstance(user_id, int) or user_id <= 0:
        return None
    return db, user_id


class CollectionCapability(BaseCapability):
    """Read and mutate collections owned by the authenticated principal."""

    @property
    def name(self) -> str:
        return "collections"

    @property
    def description(self) -> str:
        return "Read and manage the authenticated user's anime, book, music, game, and real-life collections"

    def actions(self) -> list[ActionDescriptor]:
        collection_ref = _read_schema(
            {
                "source": _COLLECTION_FIELDS["source"],
                "source_id": _COLLECTION_FIELDS["source_id"],
            },
            ["source", "source_id"],
        )
        write_ref = _schema(
            {
                "source": _COLLECTION_FIELDS["source"],
                "source_id": _COLLECTION_FIELDS["source_id"],
                "idempotency_key": {"type": "string"},
            },
            ["source", "source_id"],
        )
        write_payload = _schema(
            {**_COLLECTION_FIELDS, "idempotency_key": {"type": "string"}}
        )
        write_common: dict[str, Any] = {
            "is_side_effect": True,
            "requires_auth": True,
            "idempotency_mode": "required",
            "risk_level": "medium",
        }
        return [
            ActionDescriptor(
                name="list_collections",
                public_name="list_collections",
                description=(
                    "List one bounded page of collections owned by the authenticated "
                    "user. This action is not suitable for full-collection statistics; "
                    "use get_collection_statistics instead."
                ),
                input_schema=_read_schema(
                    {
                        "type": {"type": "integer", "enum": [1, 2, 3, 4, 6]},
                        "status": {"type": "integer", "minimum": 1, "maximum": 5},
                        "skip": {"type": "integer", "minimum": 0},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                        "sort_by": {
                            "type": "string",
                            "enum": ["updated_at", "rate", "score", "date"],
                        },
                    }
                ),
                requires_auth=True,
                output_schema=output_schema("list_collections"),
            ),
            ActionDescriptor(
                name="get_collection",
                public_name="get_collection",
                description="Get one owned collection entry and its subject",
                input_schema=collection_ref,
                requires_auth=True,
                output_schema=output_schema("get_collection"),
            ),
            ActionDescriptor(
                name="search_collections",
                public_name="search_collections",
                description="Search the authenticated user's collections by title",
                input_schema=_read_schema(
                    {
                        "keyword": {"type": "string", "minLength": 1},
                        "status": {"type": "integer", "minimum": 1, "maximum": 5},
                        "type": {"type": "integer", "enum": [1, 2, 3, 4, 6]},
                        "skip": {"type": "integer", "minimum": 0},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                        "sort_by": {
                            "type": "string",
                            "enum": ["updated_at", "rate", "score", "date"],
                        },
                    },
                    ["keyword"],
                ),
                requires_auth=True,
                output_schema=output_schema("search_collections"),
            ),
            ActionDescriptor(
                name="create_collection",
                public_name="create_collection",
                description="Create an owned collection entry",
                input_schema=_schema(
                    write_payload["properties"], ["source", "source_id", "type"]
                ),
                output_schema=write_output_schema("create_collection"),
                **write_common,
            ),
            ActionDescriptor(
                name="update_collection",
                public_name="update_collection",
                description="Update an owned collection entry",
                input_schema=_schema(
                    write_payload["properties"], ["source", "source_id"]
                ),
                output_schema=write_output_schema("update_collection"),
                **write_common,
            ),
            ActionDescriptor(
                name="delete_collection",
                public_name="delete_collection",
                description="Delete an owned collection entry",
                input_schema=write_ref,
                output_schema=write_output_schema("delete_collection"),
                **write_common,
            ),
            ActionDescriptor(
                name="upsert_collection",
                public_name="upsert_collection",
                description="Create or update one owned collection entry",
                input_schema=_schema(
                    write_payload["properties"], ["source", "source_id"]
                ),
                output_schema=write_output_schema("upsert_collection"),
                **write_common,
            ),
            ActionDescriptor(
                name="batch_upsert_collections",
                public_name="batch_upsert_collections",
                description="Create or update a bounded batch of owned collections",
                input_schema=_schema(
                    {
                        "items": {
                            "type": "array",
                            "maxItems": 100,
                            "items": _schema(
                                _COLLECTION_FIELDS, ["source", "source_id"]
                            ),
                        },
                        "idempotency_key": {"type": "string"},
                    },
                    ["items"],
                ),
                max_payload_bytes=256 * 1024,
                output_schema=write_output_schema("batch_upsert_collections"),
                **write_common,
            ),
            ActionDescriptor(
                name="import_json_collections",
                public_name="import_json_collections",
                description="Import a bounded external collection export into the owned account",
                input_schema=_schema(
                    {
                        "data": {"type": "object"},
                        "idempotency_key": {"type": "string"},
                    },
                    ["data"],
                ),
                max_payload_bytes=512 * 1024,
                output_schema=write_output_schema("import_json_collections"),
                **write_common,
            ),
            ActionDescriptor(
                name="sync_bangumi_collections",
                public_name="sync_bangumi_collections",
                description="Synchronize the authenticated user's linked Bangumi collections",
                input_schema=_schema(
                    {
                        "subject_type": {"type": "integer"},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                        "offset": {"type": "integer", "minimum": 0},
                        "idempotency_key": {"type": "string"},
                    }
                ),
                max_payload_bytes=16 * 1024,
                output_schema=write_output_schema("sync_bangumi_collections"),
                **write_common,
            ),
            ActionDescriptor(
                name="sync_douban_collections",
                public_name="sync_douban_collections",
                description="Import a bounded Douban collection export for the authenticated user",
                input_schema=_schema(
                    {
                        "data": {
                            "type": "array",
                            "maxItems": 100,
                            "items": {"type": "object"},
                        },
                        "idempotency_key": {"type": "string"},
                    },
                    ["data"],
                ),
                max_payload_bytes=512 * 1024,
                output_schema=write_output_schema("sync_douban_collections"),
                **write_common,
            ),
        ]

    async def execute(self, action: str, **kwargs: Any) -> dict[str, Any]:
        handlers = {
            "list_collections": self._list,
            "get_collection": self._get,
            "search_collections": self._search,
            "create_collection": self._create,
            "update_collection": self._update,
            "delete_collection": self._delete,
            "upsert_collection": self._upsert,
            "batch_upsert_collections": self._batch_upsert,
            "import_json_collections": self._import_json,
            "sync_bangumi_collections": self._sync_bangumi,
            "sync_douban_collections": self._sync_douban,
        }
        handler = handlers.get(action)
        if handler is None:
            return CapabilityResult.fail(
                f"Unknown action: {action}", error_type="invalid_action"
            ).to_dict()
        # Track only commits made by this business handler. Idempotency claims
        # are committed before execute(), so they cannot mark a failed write
        # as partially committed. A rollback cannot undo an earlier commit.
        db = kwargs.get("db")
        session = (
            db.sync_session
            if action in WRITE_ACTIONS and isinstance(db, AsyncSession)
            else None
        )
        committed = False

        def after_commit(_session: Any) -> None:
            nonlocal committed
            committed = True

        if session is not None:
            event.listen(session, "after_commit", after_commit)
        try:
            result = await handler(**kwargs)
            if action in WRITE_ACTIONS and result.get("success"):
                # Reject invalid JSON before the idempotency event writer can
                # turn a malformed business result into an infrastructure error.
                try:
                    json.dumps(result, allow_nan=False)
                except (TypeError, ValueError):
                    return CapabilityResult.fail(
                        "The operation state requires manual verification"
                        if committed
                        else "Collection output is not safe JSON",
                        error_type="attention_required"
                        if committed
                        else "invalid_output",
                    ).to_dict()
            return result
        except ValueError:
            return CapabilityResult.fail(
                "The operation state requires manual verification"
                if committed
                else "Invalid collection arguments",
                error_type="attention_required" if committed else "invalid_args",
            ).to_dict()
        except Exception as exc:
            logger.error(
                "collection_capability_failed",
                extra={
                    "action": action,
                    "error_type": type(exc).__name__,
                    "committed": committed,
                },
            )
            return CapabilityResult.fail(
                "The operation state requires manual verification"
                if committed
                else "Collection operation failed",
                error_type="attention_required" if committed else "internal",
            ).to_dict()
        finally:
            if session is not None:
                event.remove(session, "after_commit", after_commit)

    async def _list(self, **kwargs: Any) -> dict[str, Any]:
        trusted = _trusted(kwargs)
        if trusted is None:
            return CapabilityResult.fail(
                "Trusted db and principal are required", error_type="invalid_args"
            ).to_dict()
        db, user_id = trusted
        result = await get_user_collections(
            db,
            CollectionSearchBase(
                user_id=user_id,
                type=kwargs.get("type"),
                status=kwargs.get("status"),
                keyword=None,
                skip=kwargs.get("skip", 0),
                limit=min(kwargs.get("limit", 10), 100),
                sort_by=kwargs.get("sort_by", "updated_at"),
            ),
        )
        payload = _public(result)
        return CapabilityResult.ok(
            total=payload.get("total", 0), collections=payload.get("items", [])
        ).to_dict()

    async def _get(self, **kwargs: Any) -> dict[str, Any]:
        trusted = _trusted(kwargs)
        if trusted is None:
            return CapabilityResult.fail(
                "Trusted db and principal are required", error_type="invalid_args"
            ).to_dict()
        db, user_id = trusted
        result = await get_collection(
            db,
            CollectionSearchByID(
                user_id=user_id,
                source=kwargs["source"],
                source_id=str(kwargs["source_id"]),
            ),
        )
        if result is None:
            return CapabilityResult.fail(
                "Collection not found", error_type="not_found"
            ).to_dict()
        return CapabilityResult.ok(collection=_public(result)).to_dict()

    async def _search(self, **kwargs: Any) -> dict[str, Any]:
        trusted = _trusted(kwargs)
        if trusted is None:
            return CapabilityResult.fail(
                "Trusted db and principal are required", error_type="invalid_args"
            ).to_dict()
        db, user_id = trusted
        result = await search_collections(
            db,
            CollectionSearchByName(
                user_id=user_id,
                keyword=kwargs["keyword"],
                type=kwargs.get("type"),
                status=kwargs.get("status"),
                skip=kwargs.get("skip", 0),
                limit=min(kwargs.get("limit", 10), 100),
                sort_by=kwargs.get("sort_by", "updated_at"),
            ),
        )
        payload = _public(result)
        return CapabilityResult.ok(
            total=payload.get("total", 0), collections=payload.get("items", [])
        ).to_dict()

    async def _create(self, **kwargs: Any) -> dict[str, Any]:
        trusted = _trusted(kwargs)
        if trusted is None:
            return CapabilityResult.fail(
                "Trusted db and principal are required", error_type="invalid_args"
            ).to_dict()
        db, user_id = trusted
        data = {
            key: value for key, value in kwargs.items() if key in _COLLECTION_FIELDS
        }
        data["user_id"] = user_id
        result = await create_collection(db, CollectionCreate(**data))
        return CapabilityResult.ok(collection=_public(result)).to_dict()

    async def _update(self, **kwargs: Any) -> dict[str, Any]:
        trusted = _trusted(kwargs)
        if trusted is None:
            return CapabilityResult.fail(
                "Trusted db and principal are required", error_type="invalid_args"
            ).to_dict()
        db, user_id = trusted
        data = {
            key: value for key, value in kwargs.items() if key in _COLLECTION_FIELDS
        }
        data["user_id"] = user_id
        result = await update_collection(db, CollectionUpdate(**data))
        if result is None:
            return CapabilityResult.fail(
                "Collection not found or access denied", error_type="not_found"
            ).to_dict()
        return CapabilityResult.ok(collection=_public(result)).to_dict()

    async def _delete(self, **kwargs: Any) -> dict[str, Any]:
        trusted = _trusted(kwargs)
        if trusted is None:
            return CapabilityResult.fail(
                "Trusted db and principal are required", error_type="invalid_args"
            ).to_dict()
        db, user_id = trusted
        deleted = await delete_collection(
            db,
            CollectionSearchByID(
                user_id=user_id,
                source=kwargs["source"],
                source_id=str(kwargs["source_id"]),
            ),
        )
        if not deleted:
            return CapabilityResult.fail(
                "Collection not found or access denied", error_type="not_found"
            ).to_dict()
        return CapabilityResult.ok(deleted=True).to_dict()

    async def _upsert(self, **kwargs: Any) -> dict[str, Any]:
        trusted = _trusted(kwargs)
        if trusted is None:
            return CapabilityResult.fail(
                "Trusted db and principal are required", error_type="invalid_args"
            ).to_dict()
        db, user_id = trusted
        data = {
            key: value for key, value in kwargs.items() if key in _COLLECTION_FIELDS
        }
        result = await upsert_collection(
            db,
            user_id,
            data=CollectionUpsertRequest(
                collection=CollectionUpdate(**data), subject=None
            ).model_dump(exclude_unset=True),
        )
        return CapabilityResult.ok(collection=_public(result)).to_dict()

    async def _batch_upsert(self, **kwargs: Any) -> dict[str, Any]:
        trusted = _trusted(kwargs)
        if trusted is None:
            return CapabilityResult.fail(
                "Trusted db and principal are required", error_type="invalid_args"
            ).to_dict()
        db, user_id = trusted
        raw_items = kwargs.get("items") or []
        items = [
            CollectionUpsert(
                user_id=user_id,
                **{
                    key: value
                    for key, value in item.items()
                    if key in _COLLECTION_FIELDS
                },
            )
            for item in raw_items
        ]
        count = await batch_upsert_collections(
            db, CollectionUpsertList(total=len(items), collections=items), user_id
        )
        return CapabilityResult.ok(
            processed_count=count, requested_count=len(items)
        ).to_dict()

    async def _import_json(self, **kwargs: Any) -> dict[str, Any]:
        trusted = _trusted(kwargs)
        if trusted is None:
            return CapabilityResult.fail(
                "Trusted db and principal are required", error_type="invalid_args"
            ).to_dict()
        db, user_id = trusted
        count = await import_json_collections(db, kwargs["data"], user_id)
        return CapabilityResult.ok(processed_count=count).to_dict()

    async def _sync_bangumi(self, **kwargs: Any) -> dict[str, Any]:
        trusted = _trusted(kwargs)
        user = kwargs.get("user")
        if trusted is None or user is None:
            return CapabilityResult.fail(
                "Trusted db, principal, and linked account are required",
                error_type="invalid_args",
            ).to_dict()
        db, _ = trusted
        from app.schemas.collection import CollectionSyncRequest

        count = await sync_user_collections(
            db=db,
            user=user,
            request_data=CollectionSyncRequest(
                subject_type=kwargs.get("subject_type"),
                limit=kwargs.get("limit", 50),
                offset=kwargs.get("offset", 0),
                data=None,
            ),
        )
        return CapabilityResult.ok(processed_count=count).to_dict()

    async def _sync_douban(self, **kwargs: Any) -> dict[str, Any]:
        trusted = _trusted(kwargs)
        if trusted is None:
            return CapabilityResult.fail(
                "Trusted db and principal are required", error_type="invalid_args"
            ).to_dict()
        db, user_id = trusted
        count = await sync_user_collections_douban(user_id, db, kwargs["data"][:100])
        return CapabilityResult.ok(processed_count=count).to_dict()
