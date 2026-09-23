"""User-controlled scheduled task endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from app.api.deps import get_current_user
from app.models.agent_task import AgentTaskDef
from app.harness.scheduler.time import next_slot
from app.harness.policy import ProactivePolicy

router = APIRouter(prefix="/proactive", tags=["Proactive tasks"])


class TaskCreate(BaseModel):
    task_type: str = Field(min_length=1, max_length=100)
    payload: str = "{}"
    schedule_expr: str
    timezone: str = "Asia/Shanghai"
    catch_up: str = "latest"
    policy: str = "{}"
    idempotency_key: str | None = None
    confirm_side_effects: bool = False


class TaskUpdate(BaseModel):
    schedule_expr: str | None = None
    timezone: str | None = None
    payload: str | None = None
    policy: str | None = None
    enabled: bool | None = None
    confirm_side_effects: bool = False


def _repo(request: Request) -> Any:
    return request.app.state.proactive_repository


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_task(request: Request, body: TaskCreate, user=Depends(get_current_user)):
    try:
        policy = ProactivePolicy.from_json(body.policy)
        if policy.extra.get("requires_side_effect") and not body.confirm_side_effects:
            raise ValueError("explicit confirmation is required for side-effect tasks")
        task = AgentTaskDef(user_id=user.id, **body.model_dump())
        task.next_run = next_slot(body.schedule_expr, datetime.now(timezone.utc), body.timezone)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await _repo(request).add(task)
    return task


@router.get("/preview")
async def preview_task(
    schedule_expr: str = Query(...),
    timezone_name: str = Query("Asia/Shanghai", alias="timezone"),
    user=Depends(get_current_user),
):
    try:
        now = datetime.now(timezone.utc)
        return {"next_run": next_slot(schedule_expr, now, timezone_name)}
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.patch("/{task_id}")
async def update_task(task_id: int, request: Request, body: TaskUpdate, user=Depends(get_current_user)):
    values = body.model_dump(exclude_none=True)
    confirmation = values.pop("confirm_side_effects", False)
    try:
        if "policy" in values:
            policy = ProactivePolicy.from_json(values["policy"])
            if policy.extra.get("requires_side_effect") and not confirmation:
                raise ValueError("explicit confirmation is required for side-effect tasks")
        task = await _repo(request).update(task_id, user.id, values)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return task


@router.get("")
async def list_tasks(request: Request, user=Depends(get_current_user)):
    return await _repo(request).list_for_user(user.id)


@router.post("/{task_id}/pause")
async def pause_task(task_id: int, request: Request, user=Depends(get_current_user)):
    return await _set_enabled(request, task_id, user.id, False)


@router.post("/{task_id}/resume")
async def resume_task(task_id: int, request: Request, user=Depends(get_current_user)):
    return await _set_enabled(request, task_id, user.id, True)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(task_id: int, request: Request, user=Depends(get_current_user)):
    if not await _repo(request).delete(task_id, user.id):
        return None


@router.get("/{task_id}/runs")
async def task_runs(task_id: int, request: Request, user=Depends(get_current_user)):
    runs = await _repo(request).runs_for(task_id, user.id)
    if runs is None:
        raise HTTPException(status_code=404, detail="task not found")
    return runs


async def _set_enabled(request: Request, task_id: int, user_id: int, enabled: bool):
    task = await _repo(request).set_enabled(task_id, user_id, enabled)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return task
