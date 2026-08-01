from __future__ import annotations

import hashlib
import json
from typing import Any, Callable

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import check_qb_access, get_current_user
from app.db.database import get_session
from app.harness.persistence.idempotency import (
    IdempotencyExecution,
    IdempotencyStore,
)
from app.schemas.rss import (
    AddRssFeedRequest,
    RemoveRssItemRequest,
    RemoveRssRuleRequest,
    RssItemsResponse,
    RssRulesResponse,
    SetRssRuleRequest,
)
from app.schemas.user import UserRead
from app.services.qb_service import QBService, QBServiceError


router = APIRouter(prefix="/rss", tags=["RSS"])


def get_idempotency_store(
    db: AsyncSession = Depends(get_session),
) -> IdempotencyStore:
    return IdempotencyStore(db)


def _payload_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _scope(user: UserRead, operation: str, resource_key: str) -> str:
    resource_hash = hashlib.sha256(resource_key.encode("utf-8")).hexdigest()
    return f"principal:{user.id}|operation:{operation}|resource:{resource_hash}"


def _safe_qb_operation(operation: Callable[[], Any]) -> dict[str, Any]:
    try:
        result = operation()
        if result is None:
            return {"status": "succeeded", "message": "Operation completed."}
        if isinstance(result, dict):
            return result
        return {"status": "succeeded", "message": "Operation completed."}
    except QBServiceError as error:
        return {
            "status": "failed",
            "error_code": error.error_code,
            "message": error.message,
            "retryable": error.retryable,
        }
    except Exception:
        return {
            "status": "attention_required",
            "error_code": "operation_state_unknown",
            "message": "The operation state is unknown; manual verification is required.",
            "retryable": False,
        }


def _status_code(execution: IdempotencyExecution) -> int:
    if execution.status == "conflict":
        return 409
    if execution.result.get("status") == "attention_required":
        return 409
    if execution.result.get("error_code") == "qb_connection_error":
        return 503
    if execution.result.get("error_code") == "qb_authentication_failed":
        return 401
    if execution.result.get("status") == "failed":
        return 502
    return 200


def _write_response(execution: IdempotencyExecution) -> JSONResponse:
    content = {
        "idempotency_status": execution.status,
        **execution.result,
    }
    return JSONResponse(content=content, status_code=_status_code(execution))


async def _execute_write(
    *,
    store: Any,
    user: UserRead,
    operation_name: str,
    resource_key: str,
    idempotency_key: str,
    payload: dict[str, Any],
    operation: Callable[[], Any],
) -> JSONResponse:
    execution = await store.execute_once(
        _scope(user, operation_name, resource_key),
        idempotency_key,
        _payload_hash(payload),
        lambda: _safe_qb_operation(operation),
    )
    return _write_response(execution)


def _read_error(error: QBServiceError) -> JSONResponse:
    return JSONResponse(
        content={
            "error_code": error.error_code,
            "message": error.message,
            "retryable": error.retryable,
        },
        status_code=error.status_code,
    )


@router.get(
    "/list",
    dependencies=[Depends(check_qb_access)],
    response_model=RssItemsResponse,
)
def get_rss_list():
    try:
        return QBService().get_rss_items()
    except QBServiceError as error:
        return _read_error(error)


@router.post("/add", dependencies=[Depends(check_qb_access)])
async def add_rss_feed(
    request: AddRssFeedRequest,
    user: UserRead = Depends(get_current_user),
    store: Any = Depends(get_idempotency_store),
):
    payload = request.model_dump(exclude={"idempotency_key"}, by_alias=True)
    return await _execute_write(
        store=store,
        user=user,
        operation_name="rss.add",
        resource_key=request.name or request.url,
        idempotency_key=request.idempotency_key,
        payload=payload,
        operation=lambda: QBService().add_rss_feed(
            url=request.url,
            name=request.name,
        ),
    )


@router.post("/upsert", dependencies=[Depends(check_qb_access)])
async def upsert_rss_feed(
    request: AddRssFeedRequest,
    user: UserRead = Depends(get_current_user),
    store: Any = Depends(get_idempotency_store),
):
    payload = request.model_dump(exclude={"idempotency_key"}, by_alias=True)
    return await _execute_write(
        store=store,
        user=user,
        operation_name="rss.upsert",
        resource_key=request.name or request.url,
        idempotency_key=request.idempotency_key,
        payload=payload,
        operation=lambda: QBService().upsert_rss_feed(
            url=request.url,
            name=request.name,
        ),
    )


@router.delete("/remove", dependencies=[Depends(check_qb_access)])
async def remove_rss_item(
    request: RemoveRssItemRequest,
    user: UserRead = Depends(get_current_user),
    store: Any = Depends(get_idempotency_store),
):
    payload = request.model_dump(exclude={"idempotency_key"}, by_alias=True)
    return await _execute_write(
        store=store,
        user=user,
        operation_name="rss.remove",
        resource_key=request.item_path,
        idempotency_key=request.idempotency_key,
        payload=payload,
        operation=lambda: QBService().remove_rss_item(item_path=request.item_path),
    )


@router.post("/set-rule", dependencies=[Depends(check_qb_access)])
async def set_rss_rule(
    request: SetRssRuleRequest,
    user: UserRead = Depends(get_current_user),
    store: Any = Depends(get_idempotency_store),
):
    payload = request.model_dump(exclude={"idempotency_key"}, by_alias=True)
    return await _execute_write(
        store=store,
        user=user,
        operation_name="rss.set_rule",
        resource_key=request.rule_name,
        idempotency_key=request.idempotency_key,
        payload=payload,
        operation=lambda: QBService().set_rss_rule(
            rule_name=request.rule_name,
            rule=request.rule,
        ),
    )


@router.delete("/remove-rule", dependencies=[Depends(check_qb_access)])
async def remove_rss_rule(
    request: RemoveRssRuleRequest,
    user: UserRead = Depends(get_current_user),
    store: Any = Depends(get_idempotency_store),
):
    payload = request.model_dump(exclude={"idempotency_key"}, by_alias=True)
    return await _execute_write(
        store=store,
        user=user,
        operation_name="rss.remove_rule",
        resource_key=request.rule_name,
        idempotency_key=request.idempotency_key,
        payload=payload,
        operation=lambda: QBService().remove_rss_rule(rule_name=request.rule_name),
    )


@router.get(
    "/rules",
    dependencies=[Depends(check_qb_access)],
    response_model=RssRulesResponse,
)
def get_rss_rules():
    try:
        return QBService().get_rss_rules()
    except QBServiceError as error:
        return _read_error(error)
