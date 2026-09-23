from __future__ import annotations

import inspect
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.logging import get_logger
from app.db.database import get_session
from app.harness.persistence.collection_http import (
    CollectionHttpIdempotencyAdapter,
    HttpWriteResult,
    canonical_collection_resource_key,
    collection_http_response,
    validate_collection_item_count,
)
from app.harness.persistence.idempotency import IdempotencyStore
from app.schemas.adaptersV2 import UnifiedList
from app.schemas.collection import (
    CollectionList,
    CollectionRead,
    CollectionSearchBase,
    CollectionSearchByName,
    CollectionSyncRequest,
    CollectionUpdate,
    CollectionUpsertRequest,
)
from app.services.bangumi_service import sync_user_collections
from app.services.collection_service import (
    batch_upsert_collections,
    clear_collection_cache,
    delete_collection,
    get_collection,
    update_collection,
    upsert_collection,
)
from app.services.douban_service import sync_user_collections_douban


logger = get_logger(__name__)
router = APIRouter(prefix="/collections", tags=["Collections"])


def get_collection_idempotency_store(
    db: AsyncSession = Depends(get_session),
) -> IdempotencyStore:
    return IdempotencyStore(db)


async def _cache_outcome(user_id: int) -> dict[str, str]:
    result = clear_collection_cache(user_id)
    if inspect.isawaitable(result):
        return await result
    return result


def _request_payload(data: object) -> dict[str, Any]:
    if hasattr(data, "model_dump"):
        return data.model_dump(mode="json", exclude_unset=True)
    return data if isinstance(data, dict) else {"value": str(data)}


async def _execute_collection_write(
    *,
    store: object,
    current_user: object,
    method: str,
    resource_key: str,
    idempotency_key: str,
    payload: object,
    operation,
    item_count: int | None = None,
) -> JSONResponse:
    execution = await CollectionHttpIdempotencyAdapter(store).execute(
        principal_id=current_user.id,
        method=method,
        resource_key=resource_key,
        idempotency_key=idempotency_key,
        payload=payload,
        operation=operation,
        item_count=item_count,
    )
    return collection_http_response(execution)


@router.get("", response_model=UnifiedList)
@router.get("/", response_model=UnifiedList, include_in_schema=False)
async def get_user_collect(
    current_user=Depends(get_current_user),
    subject_type: Optional[int] = Query(None),
    status: Optional[int] = Query(None),
    keyword: Optional[str] = Query(None),
    limit: int = Query(20),
    offset: int = Query(0),
    sort_by: str = Query("updated_at"),
    db: AsyncSession = Depends(get_session),
):
    from app.models.enums import CollectionStatus
    from app.services.collection_service import get_user_collections, search_collections

    status_enum = CollectionStatus(status) if status is not None else None
    if keyword:
        search_data = CollectionSearchByName(
            user_id=current_user.id,
            status=status_enum,
            type=subject_type,
            keyword=keyword,
            sort_by=sort_by,
            limit=limit,
            skip=offset,
        )
        return await search_collections(db, search_data)
    search_data = CollectionSearchBase(
        user_id=current_user.id,
        status=status_enum,
        type=subject_type,
        limit=limit,
        skip=offset,
        sort_by=sort_by,
    )
    return await get_user_collections(db, search_data)


@router.post("/", response_model=CollectionRead)
async def create_collection(
    sid: Optional[int] = Query(None),
    data: CollectionUpsertRequest = ...,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1, max_length=128),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
    store: IdempotencyStore = Depends(get_collection_idempotency_store),
):
    async def operation() -> HttpWriteResult:
        try:
            collection = await upsert_collection(db, current_user.id, sid, data)
            source = collection.source if hasattr(collection, "source") else collection["source"]
            source_id = (
                collection.source_id
                if hasattr(collection, "source_id")
                else collection["source_id"]
            )
            from app.schemas.collection import CollectionSearchByID

            collection_read = await get_collection(
                db,
                CollectionSearchByID(
                    user_id=current_user.id,
                    source=source,
                    source_id=source_id,
                ),
            )
            if collection_read is None:
                raise HTTPException(status_code=500, detail="Collection write result unavailable")
            cache = await _cache_outcome(current_user.id)
            return HttpWriteResult(collection_read, cache_status=cache["status"])
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except Exception:
            await db.rollback()
            raise

    resource_key = (
        f"collections/subject/{sid}"
        if sid is not None
        else "collections/create"
    )
    return await _execute_collection_write(
        store=store,
        current_user=current_user,
        method="POST",
        resource_key=resource_key,
        idempotency_key=idempotency_key,
        payload={"sid": sid, "data": _request_payload(data)},
        operation=operation,
    )


@router.get("/{source}/{source_id}", response_model=CollectionRead)
async def get_collection_endpoint(
    source: str = Path(...),
    source_id: str = Path(...),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    from app.schemas.collection import CollectionSearchByID

    try:
        result = await get_collection(
            db,
            CollectionSearchByID(
                user_id=current_user.id,
                source=source,
                source_id=source_id,
            ),
        )
        if not result:
            raise HTTPException(status_code=404, detail="Collection not found")
        return result
    except HTTPException:
        raise
    except Exception as error:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Failed to get collection") from error


@router.put("/{source}/{source_id}", response_model=CollectionRead)
async def update_collection_endpoint(
    source: str = Path(...),
    source_id: str = Path(...),
    data: CollectionUpdate = ...,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1, max_length=128),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
    store: IdempotencyStore = Depends(get_collection_idempotency_store),
):
    data.source = source
    data.source_id = source_id
    data.user_id = current_user.id

    async def operation() -> HttpWriteResult:
        try:
            collection = await update_collection(db, data)
            if not collection:
                raise HTTPException(status_code=404, detail="Collection not found")
            from app.schemas.collection import CollectionSearchByID

            result = await get_collection(
                db,
                CollectionSearchByID(
                    user_id=current_user.id,
                    source=source,
                    source_id=source_id,
                ),
            )
            if result is None:
                raise HTTPException(status_code=500, detail="Collection write result unavailable")
            cache = await _cache_outcome(current_user.id)
            return HttpWriteResult(result, cache_status=cache["status"])
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except Exception:
            await db.rollback()
            raise

    return await _execute_collection_write(
        store=store,
        current_user=current_user,
        method="PUT",
        resource_key=canonical_collection_resource_key(source, source_id),
        idempotency_key=idempotency_key,
        payload={"source": source, "source_id": source_id, "data": _request_payload(data)},
        operation=operation,
    )


@router.delete("/{source}/{source_id}", response_model=dict)
async def delete_collection_endpoint(
    source: str = Path(...),
    source_id: str = Path(...),
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1, max_length=128),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
    store: IdempotencyStore = Depends(get_collection_idempotency_store),
):
    from app.schemas.collection import CollectionSearchByID

    async def operation() -> HttpWriteResult:
        try:
            deleted = await delete_collection(
                db,
                CollectionSearchByID(
                    user_id=current_user.id,
                    source=source,
                    source_id=source_id,
                ),
            )
            if not deleted:
                raise HTTPException(status_code=404, detail="Collection not found")
            cache = await _cache_outcome(current_user.id)
            return HttpWriteResult(
                {"status": "success", "message": f"Collection {source_id} deleted successfully"},
                cache_status=cache["status"],
            )
        except Exception:
            await db.rollback()
            raise

    return await _execute_collection_write(
        store=store,
        current_user=current_user,
        method="DELETE",
        resource_key=canonical_collection_resource_key(source, source_id),
        idempotency_key=idempotency_key,
        payload={"source": source, "source_id": source_id},
        operation=operation,
    )


@router.post("/batch", response_model=dict)
async def batch_upsert_collections_endpoint(
    data: CollectionList = ...,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1, max_length=128),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
    store: IdempotencyStore = Depends(get_collection_idempotency_store),
):
    item_count = validate_collection_item_count(len(data.items))

    async def operation() -> HttpWriteResult:
        try:
            success_count = await batch_upsert_collections(db, data, current_user.id)
            cache = await _cache_outcome(current_user.id)
            return HttpWriteResult(
                {
                    "status": "success",
                    "message": f"Successfully upserted {success_count}/{data.total} collections",
                    "success_count": success_count,
                    "total_count": data.total,
                },
                cache_status=cache["status"],
                item_count=item_count,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except Exception:
            await db.rollback()
            raise

    return await _execute_collection_write(
        store=store,
        current_user=current_user,
        method="POST",
        resource_key="collections/batch",
        idempotency_key=idempotency_key,
        payload=_request_payload(data),
        operation=operation,
        item_count=item_count,
    )


@router.post("/sync/bgm")
async def sync_bgm(
    data: CollectionSyncRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1, max_length=128),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
    store: IdempotencyStore = Depends(get_collection_idempotency_store),
):
    item_count = validate_collection_item_count(len(data.data or []))

    async def operation() -> HttpWriteResult:
        try:
            sync_count = await sync_user_collections(current_user, db, data)
            cache = await _cache_outcome(current_user.id)
            return HttpWriteResult(
                {
                    "message": f"Successfully synced {sync_count} collections for user {current_user.username}",
                    "username": current_user.username,
                    "sync_count": sync_count,
                    "import_count": sync_count,
                    "subject_type": data.subject_type,
                    "source": "bgm",
                },
                cache_status=cache["status"],
                item_count=sync_count,
            )
        except httpx.HTTPStatusError as error:
            if error.response.status_code == 404:
                raise HTTPException(status_code=404, detail="Bangumi user not found") from error
            raise HTTPException(status_code=502, detail="Bangumi API error") from error
        except httpx.RequestError as error:
            raise HTTPException(status_code=502, detail="Bangumi network error") from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail="Data validation failed") from error
        except Exception:
            await db.rollback()
            raise

    return await _execute_collection_write(
        store=store,
        current_user=current_user,
        method="POST",
        resource_key="collections/sync/bgm",
        idempotency_key=idempotency_key,
        payload=_request_payload(data),
        operation=operation,
        item_count=item_count,
    )


@router.post("/upload/douban")
async def upload_douban(
    data: dict,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1, max_length=128),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
    store: IdempotencyStore = Depends(get_collection_idempotency_store),
):
    if "data" in data:
        douban_data = data.get("data", [])
    elif "interest" in data:
        douban_data = data.get("interest", [])
    else:
        douban_data = data if isinstance(data, list) else []
    if not douban_data:
        raise HTTPException(status_code=400, detail="Douban data is required")
    item_count = validate_collection_item_count(len(douban_data))

    async def operation() -> HttpWriteResult:
        try:
            import_count = await sync_user_collections_douban(
                current_user.id,
                db,
                douban_data,
            )
            cache = await _cache_outcome(current_user.id)
            return HttpWriteResult(
                {
                    "message": f"Successfully imported {import_count} Douban items for user {current_user.username}",
                    "username": current_user.username,
                    "sync_count": import_count,
                    "import_count": import_count,
                    "subject_type": data.get("subject_type"),
                    "source": "douban",
                },
                cache_status=cache["status"],
                item_count=import_count,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail="Data validation failed") from error
        except Exception:
            await db.rollback()
            raise

    return await _execute_collection_write(
        store=store,
        current_user=current_user,
        method="POST",
        resource_key="collections/upload/douban",
        idempotency_key=idempotency_key,
        payload=data,
        operation=operation,
        item_count=item_count,
    )


@router.post("/sync/manual")
async def sync_manual(
    data: CollectionSyncRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1, max_length=128),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
    store: IdempotencyStore = Depends(get_collection_idempotency_store),
):
    from app.services.collection_service import import_json_collections

    if not data.data:
        raise HTTPException(status_code=400, detail="Data is required when source is 'manual'")
    item_count = validate_collection_item_count(len(data.data))

    async def operation() -> HttpWriteResult:
        try:
            sync_count = await import_json_collections(
                db,
                {"data": data.data},
                current_user.id,
            )
            cache = await _cache_outcome(current_user.id)
            return HttpWriteResult(
                {
                    "message": f"Successfully imported {sync_count} items manually for user {current_user.username}",
                    "username": current_user.username,
                    "sync_count": sync_count,
                    "subject_type": data.subject_type,
                    "source": "manual",
                },
                cache_status=cache["status"],
                item_count=item_count,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail="Data validation failed") from error
        except Exception:
            await db.rollback()
            raise

    return await _execute_collection_write(
        store=store,
        current_user=current_user,
        method="POST",
        resource_key="collections/sync/manual",
        idempotency_key=idempotency_key,
        payload=_request_payload(data),
        operation=operation,
        item_count=item_count,
    )
