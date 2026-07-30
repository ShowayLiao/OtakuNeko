// React TypeScript types for the AI workspace API — FRONTEND-AI-001 Step 01.

export interface TraceMetadata {
  trace_id: string;
  user_id?: number;
  task_id?: number;
  agent_name: string;
  goal: string;
  status: 'running' | 'completed' | 'failed' | 'cancelled';
  started_at: string;
  completed_at?: string;
  total_duration_ms?: number;
  error?: string;
  steps: TraceStep[];
}

export interface TraceStep {
  step_index: number;
  step_label: string;
  agent_name: string;
  started_at: string;
  completed_at?: string;
  status: string;
  events: TraceEvent[];
}

export interface TraceEvent {
  event_id: string;
  event_type: string;
  timestamp: string;
  data: Record<string, unknown>;
  duration_ms?: number;
  status: 'running' | 'completed' | 'failed' | 'timeout' | 'cancelled';
  correlation_id?: string;
  parent_event_id?: string;
}

export interface TraceListResponse {
  traces: TraceMetadata[];
  total: number;
  next_cursor?: string;
}

export interface TraceListParams {
  limit?: number;
  cursor?: string;
  task_id?: number;
  status?: string;
  started_after?: string;
  started_before?: string;
}

export interface ProactiveTaskDef {
  id: number;
  user_id: number;
  task_type: string;
  payload: string;
  schedule_expr: string;
  timezone: string;
  enabled: boolean;
  deleted_at?: string | null;
  next_run?: string | null;
  catch_up: 'skip' | 'latest' | 'all';
  policy: string;
  idempotency_key?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProactiveTaskRun {
  id: number;
  task_def_id: number;
  user_id: number;
  scheduled_slot: string;
  attempt: number;
  lease_id?: string | null;
  lease_expires_at?: string | null;
  status: string;
  trace_id?: string | null;
  error_category?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  created_at: string;
}

export interface TaskCreatePayload {
  task_type: string;
  payload: string;
  schedule_expr: string;
  timezone: string;
  catch_up?: 'skip' | 'latest' | 'all';
  policy?: string;
  idempotency_key?: string | null;
  confirm_side_effects?: boolean;
}

export interface TaskUpdatePayload {
  schedule_expr?: string;
  timezone?: string;
  enabled?: boolean;
  payload?: string;
  policy?: string;
  confirm_side_effects?: boolean;
}

export interface SchedulePreview {
  next_run: string;
}

export interface MemoryDeleteResponse {
  status: string;
  user_id: number;
  kind: 'episodic' | 'semantic' | 'profile' | null;
  deleted: number;
}
