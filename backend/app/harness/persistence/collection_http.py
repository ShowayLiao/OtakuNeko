"""HTTP-only idempotency adapter for Collection side effects.

The adapter keeps HTTP concerns at the boundary while reusing the durable
BATCH-06 idempotency port.  Collection is intentionally not registered as an
Agent Tool or Capability.
"""

from __future__ import annotations

import dataclasses
import hashlib
import inspect
import json
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, cast
from urllib.parse import quote

from fastapi import HTTPException
from fastapi.responses import JSONResponse

from app.harness.persistence.idempotency import (
    IdempotencyExecution,
)


MAX_IDEMPOTENCY_KEY_LENGTH = 128
MAX_COLLECTION_BATCH_ITEMS = 100


@dataclass(frozen=True)
class HttpWriteResult:
    """A serializable HTTP result plus post-commit observability metadata."""

    response: Any
    status_code: int = 200
    cache_status: str = "not_applicable"
    item_count: int | None = None


def validate_idempotency_key(value: str | None) -> str:
    if value is None or not 1 <= len(value) <= MAX_IDEMPOTENCY_KEY_LENGTH:
        raise HTTPException(
            status_code=422,
            detail=(
                "Idempotency-Key header is required and must contain between "
                "1 and 128 characters."
            ),
        )
    return value


def validate_collection_item_count(item_count: int) -> int:
    if item_count < 0 or item_count > MAX_COLLECTION_BATCH_ITEMS:
        raise HTTPException(
            status_code=413,
            detail=(
                f"Collection write requests may contain at most "
                f"{MAX_COLLECTION_BATCH_ITEMS} items."
            ),
        )
    return item_count


def canonical_collection_resource_key(source: str, source_id: str) -> str:
    normalized_source = str(source).strip().lower()
    normalized_source_id = str(source_id).strip()
    if not normalized_source or not normalized_source_id:
        raise ValueError("Collection source and source_id are required.")
    return (
        "collections/"
        f"{quote(normalized_source, safe='')}/"
        f"{quote(normalized_source_id, safe='')}"
    )


def collection_idempotency_scope(
    principal_id: int,
    method: str,
    resource_key: str,
) -> str:
    return (
        f"principal:{int(principal_id)}|method:{method.upper()}|resource:{resource_key}"
    )


def _without_request_identity(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _without_request_identity(item)
            for key, item in value.items()
            if key not in {"user_id", "principal_id"}
        }
    if isinstance(value, list):
        return [_without_request_identity(item) for item in value]
    return value


def collection_payload_hash(payload: Any) -> str:
    canonical = _without_request_identity(payload)
    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _json_safe(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if dataclasses.is_dataclass(value):
        return _json_safe(dataclasses.asdict(cast(Any, value)))
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _error_result(
    *,
    status: str,
    http_status: int,
    error_code: str,
    message: str,
    principal_id: int,
    payload_hash: str,
    item_count: int | None,
) -> dict[str, Any]:
    return {
        "status": status,
        "http_status": http_status,
        "error_code": error_code,
        "message": message,
        "retryable": http_status >= 500,
        "principal_id": principal_id,
        "payload_hash": payload_hash,
        "item_count": item_count,
    }


class CollectionHttpIdempotencyAdapter:
    """Claim and persist one Collection HTTP write outcome."""

    def __init__(self, store: Any) -> None:
        self._store = store

    async def execute(
        self,
        *,
        principal_id: int,
        method: str,
        resource_key: str,
        idempotency_key: str,
        payload: Any,
        operation: Callable[[], Any | Awaitable[Any]],
        item_count: int | None = None,
    ) -> IdempotencyExecution:
        key = validate_idempotency_key(idempotency_key)
        if item_count is not None:
            validate_collection_item_count(item_count)
        payload_hash = collection_payload_hash(payload)
        scope = collection_idempotency_scope(principal_id, method, resource_key)

        async def safe_operation() -> dict[str, Any]:
            try:
                value = operation()
                if inspect.isawaitable(value):
                    value = await value
                if isinstance(value, HttpWriteResult):
                    return {
                        "status": "succeeded",
                        "http_status": value.status_code,
                        "response": _json_safe(value.response),
                        "cache_status": value.cache_status,
                        "principal_id": principal_id,
                        "payload_hash": payload_hash,
                        "item_count": (
                            value.item_count
                            if value.item_count is not None
                            else item_count
                        ),
                    }
                return {
                    "status": "succeeded",
                    "http_status": 200,
                    "response": _json_safe(value),
                    "cache_status": "not_applicable",
                    "principal_id": principal_id,
                    "payload_hash": payload_hash,
                    "item_count": item_count,
                }
            except HTTPException as error:
                detail = (
                    error.detail
                    if isinstance(error.detail, str)
                    else "HTTP operation failed."
                )
                return _error_result(
                    status="failed",
                    http_status=error.status_code,
                    error_code=f"http_{error.status_code}",
                    message=detail,
                    principal_id=principal_id,
                    payload_hash=payload_hash,
                    item_count=item_count,
                )
            except ValueError as error:
                return _error_result(
                    status="failed",
                    http_status=400,
                    error_code="collection_validation_failed",
                    message=str(error),
                    principal_id=principal_id,
                    payload_hash=payload_hash,
                    item_count=item_count,
                )
            except Exception:
                return _error_result(
                    status="attention_required",
                    http_status=500,
                    error_code="collection_write_state_unknown",
                    message=(
                        "The Collection write state is unknown; manual verification "
                        "is required."
                    ),
                    principal_id=principal_id,
                    payload_hash=payload_hash,
                    item_count=item_count,
                )

        return await self._store.execute_once(
            scope,
            key,
            payload_hash,
            safe_operation,
        )


def collection_http_response(execution: IdempotencyExecution) -> JSONResponse:
    result = execution.result
    if execution.status == "conflict":
        status_code = 409
        content: Any = result
    else:
        status_code = int(result.get("http_status", 200))
        content = result.get("response")
        if content is None:
            content = {
                key: result[key]
                for key in ("status", "error_code", "message", "retryable")
                if key in result
            }
        if result.get("status") == "attention_required":
            status_code = 409

    headers = {
        "X-Idempotency-Status": execution.status,
        "X-Collection-Cache-Status": str(result.get("cache_status", "not_applicable")),
    }
    return JSONResponse(content=content, status_code=status_code, headers=headers)


__all__ = [
    "CollectionHttpIdempotencyAdapter",
    "HttpWriteResult",
    "MAX_COLLECTION_BATCH_ITEMS",
    "canonical_collection_resource_key",
    "collection_http_response",
    "collection_idempotency_scope",
    "collection_payload_hash",
    "validate_collection_item_count",
    "validate_idempotency_key",
]
