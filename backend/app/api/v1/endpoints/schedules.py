from fastapi import APIRouter, Depends, Header, HTTPException, Path
from typing import Any, Callable, List
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_session
from app.api.deps import get_current_user
from app.services.schedule_service import ScheduleService
from app.schemas.schedule import ScheduleRead, ScheduleCreate, ScheduleUpdate, ScheduleUpsert, ScheduleUpsertList, ScheduleReadList, UnifiedScheduleList
from app.schemas.adaptersV2 import UnifiedList
from app.core.logging import get_logger
from app.capabilities.factory import build_capability_registry
from app.harness.capability_adapter import CapabilityAdapter
from app.harness.contracts import AgentDecision, ExecutionContext
from app.harness.dispatcher import Dispatcher
from app.harness.persistence.idempotency import SqlIdempotencyStore
from app.harness.policy import Approval, PolicyEngine

router = APIRouter(prefix="/schedules", tags=["Schedules"])

logger = get_logger(__name__)


def _require_idempotency_key(value: str | None) -> str:
    if value is None or not value.strip():
        raise HTTPException(status_code=422, detail="Idempotency-Key is required")
    return value.strip()


async def _dispatch_schedule_write(
    *,
    action: str,
    arguments: dict[str, Any],
    user_id: int,
    idempotency_key: str,
    db: AsyncSession,
) -> dict[str, Any]:
    """Use the canonical Registry -> Policy -> Dispatcher -> Adapter path."""
    registry = build_capability_registry()
    policy_engine = PolicyEngine(allow_side_effects=True)
    approval = Approval(
        approval_id=f"http:{user_id}:{idempotency_key}",
        principal_id=user_id,
        action=action,
    )
    idempotency_store = SqlIdempotencyStore(db)

    def adapter_factory(capability: Any) -> CapabilityAdapter:
        return CapabilityAdapter(
            capability,
            policy_engine=policy_engine,
            approval=approval,
            idempotency_store=idempotency_store,
            trusted_args={"db": db},
        )

    run_id = f"http-schedule:{uuid4().hex}"
    dispatcher = Dispatcher(
        registry,
        policy_engine=policy_engine,
        approval=approval,
        idempotency_store=idempotency_store,
        adapter_factory=adapter_factory,
    )
    result = await dispatcher.dispatch(
        AgentDecision(
            decision_id=uuid4().hex,
            run_id=run_id,
            action="invoke",
            capability=action,
            capability_version="v1",
            arguments={**arguments, "idempotency_key": idempotency_key},
        ),
        ExecutionContext(
            principal_id=user_id,
            run_id=run_id,
            trace_id=run_id,
            capability_allowlist=frozenset({action}),
        ),
        idempotency_key=idempotency_key,
    )
    if result.status == "succeeded":
        return result.output
    error_type = str(result.error_code or result.output.get("error_type", "tool_error"))
    status_code = {
        "unauthorized": 401,
        "policy_denied": 403,
        "idempotency_required": 422,
        "idempotency_conflict": 409,
        "not_found": 404,
    }.get(error_type, 502)
    raise HTTPException(status_code=status_code, detail="Schedule operation was not completed")


async def _execute_schedule_write_once(
    *,
    operation_name: str,
    resource_key: str,
    idempotency_key: str,
    payload: dict[str, Any],
    user_id: int,
    db: AsyncSession,
    operation: Callable[[], Any],
) -> dict[str, Any]:
    """Use the same durable idempotency contract for legacy bulk operations."""
    import hashlib
    import json

    payload_hash = hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()
    execution = await SqlIdempotencyStore(db).execute_once(
        f"{user_id}:schedule:{operation_name}:{resource_key}",
        idempotency_key,
        payload_hash,
        operation,
    )
    if execution.status == "conflict":
        raise HTTPException(status_code=409, detail="Idempotency key conflict")
    if execution.result.get("status") == "attention_required":
        raise HTTPException(status_code=409, detail="Operation requires manual verification")
    if execution.result.get("status") != "succeeded":
        if execution.result.get("error_code") == "not_found":
            raise HTTPException(status_code=404, detail="Schedule not found or access denied")
        raise HTTPException(status_code=502, detail="Schedule operation was not completed")
    return execution.result.get("data", {})


async def _upsert_result(
    db: AsyncSession,
    user_id: int,
    schedule_data: ScheduleUpsert,
) -> dict[str, Any]:
    result = await ScheduleService.upsert_schedule(db, user_id, schedule_data)
    if result is None:
        return {"status": "failed", "error_code": "not_found"}
    return {"status": "succeeded", "data": result.model_dump()}


async def _bulk_upsert_result(
    db: AsyncSession,
    user_id: int,
    upsert_list: ScheduleUpsertList,
) -> dict[str, Any]:
    results = await ScheduleService.bulk_upsert_schedules(db, user_id, upsert_list)
    return {
        "status": "succeeded",
        "data": {"items": [item.model_dump() for item in results]},
    }


async def _delete_all_result(db: AsyncSession, user_id: int) -> dict[str, Any]:
    deleted = await ScheduleService.delete_all_schedules(db, user_id)
    return {
        "status": "succeeded",
        "data": {
            "status": "success",
            "message": (
                "All schedule records deleted"
                if deleted
                else "No schedule records to delete"
            ),
        },
    }


async def _sync_bangumi_result(db: AsyncSession, user_id: int) -> dict[str, Any]:
    result = await ScheduleService.sync_bangumi_calendar(db, user_id)
    return {"status": "succeeded", "data": result.model_dump()}


@router.get("/", response_model=UnifiedScheduleList)
async def get_user_schedules(
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """
    获取当前用户的所有排班记录，附带关联的条目和收藏信息
    
    Args:
        current_user: 当前认证用户
        db: 数据库会话
        
    Returns:
        当前用户的所有排班记录列表，包含关联的条目和收藏信息
        
    Raises:
        HTTPException: 当获取失败时返回错误
    """
    try:
        schedules = await ScheduleService.get_unified_user_schedules(db, current_user.id)
        return schedules
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取排班记录失败: {str(e)}")


@router.get("/by-day/{day}", response_model=List[ScheduleRead])
async def get_schedules_by_day(
    day: int = Path(..., ge=0, le=6, description="星期几，0-6 (周日到周六)"),
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """
    获取当前用户指定星期的排班记录
    
    Args:
        day: 星期几，0-6 (周日到周六)
        current_user: 当前认证用户
        db: 数据库会话
        
    Returns:
        指定星期的排班记录列表
        
    Raises:
        HTTPException: 当获取失败时返回错误
    """
    try:
        schedules = await ScheduleService.get_schedules_by_day(db, current_user.id, day)
        return schedules
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取指定星期的排班记录失败: {str(e)}")


@router.post("/", response_model=ScheduleRead, status_code=201)
async def create_schedule(
    schedule_data: ScheduleCreate,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1, max_length=128),
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """
    为当前用户创建新的排班记录
    
    Args:
        schedule_data: 排班数据，使用 ScheduleCreate schema
        current_user: 当前认证用户
        db: 数据库会话
        
    Returns:
        创建的排班记录
        
    Raises:
        HTTPException: 当创建失败时返回错误
    """
    try:
        key = _require_idempotency_key(idempotency_key)
        output = await _dispatch_schedule_write(
            action="create_schedule",
            arguments=schedule_data.model_dump(exclude={"user_id"}, exclude_none=True),
            user_id=current_user.id,
            idempotency_key=key,
            db=db,
        )
        new_schedule = output.get("schedule")
        if not new_schedule:
            raise HTTPException(status_code=409, detail="排班记录已存在")
        return new_schedule
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建排班记录失败: {str(e)}")


@router.put("/{id}", response_model=ScheduleRead)
async def update_schedule(
    id: int,
    schedule_data: ScheduleUpdate,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1, max_length=128),
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """
    更新当前用户的排班记录
    
    Args:
        id: 排班ID
        schedule_data: 更新的排班数据，使用 ScheduleUpdate schema
        current_user: 当前认证用户
        db: 数据库会话
        
    Returns:
        更新后的排班记录
        
    Raises:
        HTTPException: 当更新失败或记录不存在时返回错误
    """
    try:
        key = _require_idempotency_key(idempotency_key)
        output = await _dispatch_schedule_write(
            action="update_schedule",
            arguments={
                "schedule_id": id,
                **schedule_data.model_dump(exclude_none=True),
            },
            user_id=current_user.id,
            idempotency_key=key,
            db=db,
        )
        updated_schedule = output.get("schedule")
        if not updated_schedule:
            raise HTTPException(status_code=404, detail="排班记录不存在或不属于当前用户")
        return updated_schedule
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新排班记录失败: {str(e)}")


@router.delete("/all", response_model=dict, status_code=200)
async def delete_all_schedules(
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1, max_length=128),
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """
    删除当前用户的所有排班记录
    
    Args:
        current_user: 当前认证用户
        db: 数据库会话
        
    Returns:
        删除结果，包含成功状态和消息
        
    Raises:
        HTTPException: 当删除失败时返回错误
    """
    try:
        key = _require_idempotency_key(idempotency_key)
        return await _execute_schedule_write_once(
            operation_name="delete_all",
            resource_key="all",
            idempotency_key=key,
            payload={},
            user_id=current_user.id,
            db=db,
            operation=lambda: _delete_all_result(db, current_user.id),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除所有排班记录失败: {str(e)}")


@router.delete("/{id}", response_model=dict, status_code=200)
async def delete_schedule(
    id: int,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1, max_length=128),
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """
    删除当前用户的排班记录
    
    Args:
        id: 排班ID
        current_user: 当前认证用户
        db: 数据库会话
        
    Returns:
        删除结果，包含成功状态和消息
        
    Raises:
        HTTPException: 当删除失败或记录不存在时返回错误
    """
    try:
        key = _require_idempotency_key(idempotency_key)
        output = await _dispatch_schedule_write(
            action="delete_schedule",
            arguments={"schedule_id": id},
            user_id=current_user.id,
            idempotency_key=key,
            db=db,
        )
        if not output.get("deleted"):
            raise HTTPException(status_code=404, detail="排班记录不存在或不属于当前用户")
        return {"status": "success", "message": "排班记录删除成功"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除排班记录失败: {str(e)}")


@router.post("/upsert", response_model=ScheduleRead)
async def upsert_schedule(
    schedule_data: ScheduleUpsert,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1, max_length=128),
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """
    Upsert 当前用户的排班记录（更新或插入）
    
    Args:
        schedule_data: 排班数据，使用 ScheduleUpsert schema
        current_user: 当前认证用户
        db: 数据库会话
        
    Returns:
        处理后的排班记录
        
    Raises:
        HTTPException: 当处理失败时返回错误
    """
    try:
        key = _require_idempotency_key(idempotency_key)
        trusted_data = schedule_data.model_copy(update={"user_id": current_user.id})
        payload = trusted_data.model_dump(exclude={"user_id"}, exclude_none=True)
        result = await _execute_schedule_write_once(
            operation_name="upsert",
            resource_key=str(trusted_data.id or "collection"),
            idempotency_key=key,
            payload=payload,
            user_id=current_user.id,
            db=db,
            operation=lambda: _upsert_result(db, current_user.id, trusted_data),
        )
        if not result:
            raise HTTPException(status_code=404, detail="排班记录不存在或不属于当前用户")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upsert 排班记录失败: {str(e)}")


@router.post("/bulk-upsert", response_model=ScheduleReadList)
async def bulk_upsert_schedules(
    upsert_list: ScheduleUpsertList,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1, max_length=128),
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """
    批量 Upsert 当前用户的排班记录
    
    Args:
        upsert_list: 待处理的排班记录列表
        current_user: 当前认证用户
        db: 数据库会话
        
    Returns:
        处理后的排班记录列表
        
    Raises:
        HTTPException: 当处理失败时返回错误
    """
    try:
        key = _require_idempotency_key(idempotency_key)
        trusted_list = upsert_list.model_copy(
            update={
                "items": [
                    item.model_copy(update={"user_id": current_user.id})
                    for item in upsert_list.items
                ]
            }
        )
        payload = {
            "items": [
                item.model_dump(exclude={"user_id"}, exclude_none=True)
                for item in trusted_list.items
            ]
        }
        data = await _execute_schedule_write_once(
            operation_name="bulk_upsert",
            resource_key="collection",
            idempotency_key=key,
            payload=payload,
            user_id=current_user.id,
            db=db,
            operation=lambda: _bulk_upsert_result(db, current_user.id, trusted_list),
        )
        results = data.get("items", [])
        return {
            "items": results,
            "total": len(results)
        }
    except Exception as e:
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(status_code=500, detail=f"批量 Upsert 排班记录失败: {str(e)}")


@router.post("/sync-bangumi", response_model=UnifiedList)
async def sync_bangumi_calendar(
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1, max_length=128),
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """
    同步 Bangumi 日历数据
    
    步骤：
    1. 获取 Bangumi 日历数据
    2. 转换为 SubjectUpsertList
    3. 批量插入数据
    4. 批量同步番剧放送时间
    5. 转换为统一格式返回
    
    Args:
        current_user: 当前认证用户
        db: 数据库会话
        
    Returns:
        转换后的统一格式数据列表
        
    Raises:
        HTTPException: 当同步失败时返回错误
    """
    try:
        key = _require_idempotency_key(idempotency_key)
        return await _execute_schedule_write_once(
            operation_name="sync_bangumi",
            resource_key="calendar",
            idempotency_key=key,
            payload={},
            user_id=current_user.id,
            db=db,
            operation=lambda: _sync_bangumi_result(db, current_user.id),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"同步 Bangumi 日历数据失败: {str(e)}")
