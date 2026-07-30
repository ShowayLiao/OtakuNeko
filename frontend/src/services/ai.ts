// AI workspace service client — FRONTEND-AI-001 Step 01.

import { request } from '@/services/client';
import type {
  TraceMetadata,
  TraceListResponse,
  TraceListParams,
  ProactiveTaskDef,
  ProactiveTaskRun,
  TaskCreatePayload,
  TaskUpdatePayload,
  SchedulePreview,
  MemoryDeleteResponse,
} from '@/types/ai';

// ---------------------------------------------------------------------------
// Trace API
// ---------------------------------------------------------------------------

export async function listTraces(params: TraceListParams = {}): Promise<TraceListResponse> {
  const query = new URLSearchParams();
  if (params.limit !== undefined) query.set('limit', String(params.limit));
  if (params.cursor !== undefined) query.set('cursor', params.cursor);
  if (params.task_id !== undefined) query.set('task_id', String(params.task_id));
  if (params.status !== undefined) query.set('status', params.status);
  if (params.started_after !== undefined) query.set('started_after', params.started_after);
  if (params.started_before !== undefined) query.set('started_before', params.started_before);
  const qs = query.toString();
  return request<TraceListResponse>(`/trace${qs ? `?${qs}` : ''}`);
}

export async function getTrace(traceId: string): Promise<TraceMetadata> {
  return request<TraceMetadata>(`/trace/${traceId}`);
}

// ---------------------------------------------------------------------------
// Proactive Task API
// ---------------------------------------------------------------------------

export async function listTasks(): Promise<ProactiveTaskDef[]> {
  return request<ProactiveTaskDef[]>('/proactive');
}

export async function createTask(payload: TaskCreatePayload): Promise<ProactiveTaskDef> {
  return request<ProactiveTaskDef>('/proactive', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function updateTask(id: number, payload: TaskUpdatePayload): Promise<ProactiveTaskDef> {
  return request<ProactiveTaskDef>(`/proactive/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export async function pauseTask(id: number): Promise<ProactiveTaskDef> {
  return request<ProactiveTaskDef>(`/proactive/${id}/pause`, { method: 'POST' });
}

export async function resumeTask(id: number): Promise<ProactiveTaskDef> {
  return request<ProactiveTaskDef>(`/proactive/${id}/resume`, { method: 'POST' });
}

export async function deleteTask(id: number): Promise<void> {
  await request<void>(`/proactive/${id}`, { method: 'DELETE' });
}

export async function getTaskRuns(taskDefId: number): Promise<ProactiveTaskRun[]> {
  return request<ProactiveTaskRun[]>(`/proactive/${taskDefId}/runs`);
}

export async function previewSchedule(
  scheduleExpr: string,
  timezone: string,
): Promise<SchedulePreview> {
  const query = new URLSearchParams({
    schedule_expr: scheduleExpr,
    timezone,
  });
  return request<SchedulePreview>(`/proactive/preview?${query.toString()}`, {
    method: 'GET',
  });
}

// ---------------------------------------------------------------------------
// Memory API
// ---------------------------------------------------------------------------

export async function deleteUserMemory(kind?: string): Promise<MemoryDeleteResponse> {
  const query = kind ? `?kind=${encodeURIComponent(kind)}` : '';
  return request<MemoryDeleteResponse>(`/memory${query}`, {
    method: 'DELETE',
  });
}
