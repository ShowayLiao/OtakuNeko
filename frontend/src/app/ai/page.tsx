"use client";

import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useCallback, useEffect, useState } from 'react';
import { Tabs } from 'antd';
import { Activity, Calendar, Settings } from 'lucide-react';
import { Flexbox } from '@lobehub/ui';
import {
  deleteUserMemory,
  listTasks,
  listTraces,
} from '@/services/ai';
import type {
  MemoryDeleteResponse,
  ProactiveTaskDef,
  TraceMetadata,
} from '@/types/ai';

export default function AIPage() {
  return (
    <Suspense fallback={<div>Loading...</div>}>
      <AIWorkspace />
    </Suspense>
  );
}

function AIWorkspace() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const router = useRouter();
  const section = searchParams.get('section') || 'traces';

  const items = [
    {
      key: 'traces',
      label: 'Observability',
      icon: <Activity size={16} />,
      children: <TracePanel />,
    },
    {
      key: 'tasks',
      label: 'Scheduled Tasks',
      icon: <Calendar size={16} />,
      children: <TaskPanel />,
    },
    {
      key: 'settings',
      label: 'Memory',
      icon: <Settings size={16} />,
      children: <SettingsPanel />,
    },
  ];

  const validSections = items.map((i) => i.key);
  const activeSection = validSections.includes(section) ? section : 'traces';

  return (
    <Flexbox
      style={{
        height: '100%',
        padding: 24,
        overflow: 'auto',
      }}
    >
      <div style={{ marginBottom: 16 }}>
        <h2 style={{ margin: 0, fontSize: 20, fontWeight: 600 }}>AI Workspace</h2>
        <p style={{ margin: '4px 0 0', opacity: 0.65 }}>
          Observability, scheduled tasks, and memory controls
        </p>
      </div>

      <Tabs
        activeKey={activeSection}
        onChange={(key) => router.replace(`${pathname}?section=${key}`)}
        items={items}
        style={{ flex: 1 }}
      />
    </Flexbox>
  );
}

const panelStyle = {
  border: '1px solid rgba(127, 127, 127, 0.24)',
  borderRadius: 12,
  padding: 16,
} as const;

const rowStyle = {
  borderBottom: '1px solid rgba(127, 127, 127, 0.16)',
  padding: '12px 0',
} as const;

function TracePanel() {
  const [traces, setTraces] = useState<TraceMetadata[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>();

  const load = useCallback(async () => {
    setLoading(true);
    setError(undefined);
    try {
      const result = await listTraces({ limit: 20 });
      setTraces(result.traces);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to load traces');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <section aria-labelledby="trace-panel-title" style={panelStyle}>
      <PanelHeader
        actionLabel="Refresh traces"
        loading={loading}
        onAction={load}
        title="Recent traces"
        titleId="trace-panel-title"
      />
      {error && <p role="alert">{error}</p>}
      {!loading && !error && traces.length === 0 && <p>No traces recorded yet.</p>}
      {traces.map((trace) => (
        <article key={trace.trace_id} style={rowStyle}>
          <strong>{trace.goal || trace.agent_name || trace.trace_id}</strong>
          <div>
            <span>{trace.status}</span>
            {' · '}
            <time dateTime={trace.started_at}>
              {new Date(trace.started_at).toLocaleString()}
            </time>
          </div>
          <small>Trace {trace.trace_id}</small>
        </article>
      ))}
    </section>
  );
}

function TaskPanel() {
  const [tasks, setTasks] = useState<ProactiveTaskDef[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>();

  const load = useCallback(async () => {
    setLoading(true);
    setError(undefined);
    try {
      setTasks(await listTasks());
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to load tasks');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <section aria-labelledby="task-panel-title" style={panelStyle}>
      <PanelHeader
        actionLabel="Refresh tasks"
        loading={loading}
        onAction={load}
        title="Scheduled tasks"
        titleId="task-panel-title"
      />
      {error && <p role="alert">{error}</p>}
      {!loading && !error && tasks.length === 0 && <p>No scheduled tasks.</p>}
      {tasks.map((task) => (
        <article key={task.id} style={rowStyle}>
          <strong>{task.task_type}</strong>
          <div>
            <code>{task.schedule_expr}</code>
            {' · '}
            <span>{task.timezone}</span>
            {' · '}
            <span>{task.enabled ? 'enabled' : 'paused'}</span>
          </div>
          {task.next_run && (
            <small>
              Next run <time dateTime={task.next_run}>{new Date(task.next_run).toLocaleString()}</time>
            </small>
          )}
        </article>
      ))}
    </section>
  );
}

function SettingsPanel() {
  const [deleting, setDeleting] = useState(false);
  const [result, setResult] = useState<MemoryDeleteResponse>();
  const [error, setError] = useState<string>();

  const clearAllMemory = async () => {
    if (!window.confirm('Delete all saved AI memory for your account?')) {
      return;
    }
    setDeleting(true);
    setError(undefined);
    setResult(undefined);
    try {
      setResult(await deleteUserMemory());
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to delete memory');
    } finally {
      setDeleting(false);
    }
  };

  return (
    <section aria-labelledby="settings-panel-title" style={panelStyle}>
      <h3 id="settings-panel-title">Memory controls</h3>
      <p>
        Memory is private to your account. The current API supports deletion,
        not browsing or exporting saved records.
      </p>
      <button disabled={deleting} onClick={clearAllMemory} type="button">
        {deleting ? 'Deleting…' : 'Delete all memory'}
      </button>
      {error && <p role="alert">{error}</p>}
      {result && (
        <p aria-live="polite">Deleted {result.deleted} memory records.</p>
      )}
    </section>
  );
}

function PanelHeader({
  actionLabel,
  loading,
  onAction,
  title,
  titleId,
}: {
  actionLabel: string;
  loading: boolean;
  onAction: () => Promise<void>;
  title: string;
  titleId: string;
}) {
  return (
    <div style={{ alignItems: 'center', display: 'flex', justifyContent: 'space-between' }}>
      <h3 id={titleId}>{title}</h3>
      <button disabled={loading} onClick={() => void onAction()} type="button">
        {loading ? 'Loading…' : actionLabel}
      </button>
    </div>
  );
}
