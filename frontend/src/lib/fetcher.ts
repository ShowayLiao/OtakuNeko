/* eslint-disable @typescript-eslint/no-explicit-any -- SSE payloads are provider-defined JSON. */
import { useApiStore } from '@/store/useApiStore';
import type { RunPhase, RunTerminalStatus, RunView } from '@/stores/useChatStore';

interface PromptConfig {
  persona: string;
  tone: string;
  rules: string;
}

interface DeepSeekOptions {
  thinking: boolean;
  reasoning_effort: 'high' | 'max';
}

type SSEData = Record<string, unknown>;

interface ParsedSSEEvent {
  type: string;
  data: SSEData;
  id?: string;
}

type TerminalStatus = 'succeeded' | 'failed' | 'cancelled' | 'timeout';

export const AUTH_STATE_CHANGED_EVENT = 'otakuneko-auth-state-changed';

export interface CurrentUser {
  id: number;
  username: string;
  avatar_url: string | null;
  bangumi_id: number | null;
  bangumi_name?: string | null;
  sign: string | null;
  created_at: string;
}

const invalidateAuth = () => {
  localStorage.removeItem('token');
  window.dispatchEvent(new Event(AUTH_STATE_CHANGED_EVENT));
};

interface NormalizedTerminalStatus {
  status: TerminalStatus;
  error_code: string | null;
}

interface ChatWithBackendOptions {
  messages: unknown[];
  provider: string;
  model?: string;
  temperature?: number;
  prompt_config?: PromptConfig;
  thread_id?: string;
  abortSignal?: AbortSignal;
  onMessageChunk?: (chunk: string) => void;
  onMessageStart?: () => void;
  onMessageEnd?: () => void;
  onToolCallStart?: (id: string, name: string, inputs: unknown) => void;
  onToolCallEnd?: (
    id: string,
    name: string,
    output: unknown,
    durationMs?: number,
    status?: string,
    errorCode?: string | null,
  ) => void;
  onToolCallDelta?: (id: string, name: string, delta: string) => void;
  onPlanUpdate?: (plan: string) => void;
  onProgress?: (data: { tool_name: string; tool_count: number; duration_ms: number }) => void;
  onConnectionStatus?: (status: 'connected' | 'connecting' | 'disconnected') => void;
  onThinkingStart?: () => void;
  onThinkingChunk?: (chunk: string) => void;
  onThinkingEnd?: () => void;
  onError?: (error: string, errorCode?: string | null) => void;
  onRunStatus?: (status: {
    run_id: string;
    status: string;
    error_code?: string | null;
    last_sequence?: number;
  }) => void;
  onRunView?: (view: RunView) => void;
  resumeRun?: {
    runId: string;
    after?: number;
    durable?: boolean | null;
    threadId?: string;
  };
  onComplete?: (metadata?: {
    hasDurableRun: boolean;
    terminalStatus: TerminalStatus | null;
  }) => void;
}

const toSequence = (value: unknown): number | null => {
  const numericValue = typeof value === 'number'
    ? value
    : typeof value === 'string' && value.trim() !== ''
      ? Number(value)
      : Number.NaN;
  return Number.isSafeInteger(numericValue) && numericValue >= 0
    ? numericValue
    : null;
};

const maxSequence = (...values: unknown[]): number | null => {
  const sequences = values
    .map(toSequence)
    .filter((value): value is number => value !== null);
  return sequences.length > 0 ? Math.max(...sequences) : null;
};

const normalizedString = (value: unknown): string | null => (
  typeof value === 'string' && value.trim() !== ''
    ? value.trim().toLowerCase()
    : null
);

const terminalStatusFromValue = (value: unknown): TerminalStatus | null => {
  switch (normalizedString(value)) {
    case 'succeeded':
    case 'success':
    case 'completed':
      return 'succeeded';
    case 'cancelled':
    case 'canceled':
      return 'cancelled';
    case 'timeout':
    case 'timed_out':
    case 'timed-out':
      return 'timeout';
    case 'failed':
    case 'failure':
    case 'error':
      return 'failed';
    default:
      return null;
  }
};

const normalizeTerminalStatus = (
  eventType: string,
  data: SSEData,
): NormalizedTerminalStatus | null => {
  const errorCode = typeof data.error_code === 'string' ? data.error_code : null;
  const statusMarker = terminalStatusFromValue(data.status);
  const errorMarker = terminalStatusFromValue(data.error_code);
  let status: TerminalStatus | null = null;

  switch (eventType) {
    case 'run_completed':
    case 'run.succeeded':
      status = 'succeeded';
      break;
    case 'run_cancelled':
    case 'run.cancelled':
      status = 'cancelled';
      break;
    case 'run_timeout':
      status = 'timeout';
      break;
    case 'run_failed':
    case 'run.failed':
      status = statusMarker === 'timeout' || errorMarker === 'timeout'
        ? 'timeout'
        : 'failed';
      break;
    case 'run_status':
      status = statusMarker;
      break;
    default:
      break;
  }

  if (!status) return null;
  return {
    status,
    error_code: errorCode || (status === 'timeout' ? 'timeout' : null),
  };
};

const stringValue = (value: unknown): string | null => (
  typeof value === 'string' && value.trim() !== '' ? value : null
);

const numberValue = (value: unknown, fallback = 0): number => {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return fallback;
};

const optionalNumberValue = (value: unknown): number | undefined => {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return undefined;
};

const normalizeArgumentKeys = (value: unknown): string[] => {
  const keys = Array.isArray(value)
    ? value.filter((item): item is string => typeof item === 'string')
    : value && typeof value === 'object'
      ? Object.keys(value)
      : [];
  return keys
    .map(key => key.trim())
    .filter(Boolean)
    .slice(0, 32);
};

const normalizeInvocationStatus = (status: unknown, errorCode: unknown): string => {
  const statusMarker = normalizedString(status);
  const errorMarker = normalizedString(errorCode);
  if (statusMarker === 'timeout' || statusMarker === 'timed_out' || errorMarker === 'timeout') {
    return 'timeout';
  }
  if (statusMarker === 'denied' || statusMarker === 'forbidden') return 'denied';
  if (statusMarker === 'cancelled' || statusMarker === 'canceled') return 'cancelled';
  if (statusMarker === 'succeeded' || statusMarker === 'success' || statusMarker === 'completed') {
    return 'succeeded';
  }
  return 'failed';
};

const phaseForEvent = (eventType: string): RunPhase | null => {
  switch (eventType) {
    case 'model_decision':
    case 'thinking_start':
    case 'thinking_chunk':
    case 'thinking_end':
    case 'reasoning_chunk':
      return 'thinking';
    case 'tool_call_delta':
    case 'tool_call_start':
    case 'tool_call_end':
    case 'tool_start':
    case 'tool_end':
      return 'executing';
    case 'message_start':
    case 'message_chunk':
    case 'message_end':
      return 'responding';
    default:
      return null;
  }
};

const phaseForTerminalStatus = (status: RunTerminalStatus): RunPhase => {
  switch (status) {
    case 'succeeded': return 'completed';
    case 'cancelled': return 'cancelled';
    case 'timeout': return 'timeout';
    case 'failed': return 'failed';
  }
};

// 解析 SSE 事件流
const parseSSE = (text: string): ParsedSSEEvent[] => {
  const events: ParsedSSEEvent[] = [];
  const lines = text.split('\n');
  let event: { type: string; data: string; id?: string } = { type: 'message', data: '' };
  
  for (const line of lines) {
    if (line.startsWith('id:')) {
      event.id = line.substring(3).trim();
    } else if (line.startsWith('event:')) {
      event.type = line.substring(6).trim();
    } else if (line.startsWith('data:')) {
      event.data += line.substring(5).trim() + '\n';
    } else if (line === '') {
      if (event.data) {
        try {
          const data = JSON.parse(event.data.trim());
          if (typeof data === 'object' && data !== null) {
            events.push({ type: event.type, data: data as SSEData, id: event.id });
          }
        } catch {
          // 忽略解析错误
        }
        event = { type: 'message', data: '' };
      }
    }
  }
  
  return events;
};

export const chatWithBackend = async ({
  messages,
  provider,
  model = 'gpt-3.5-turbo',
  temperature = 0.7,
  prompt_config,
  thread_id,
  abortSignal,
  onMessageChunk,
  onMessageStart,
  onMessageEnd,
  onToolCallStart,
  onToolCallEnd,
  onToolCallDelta,
  onPlanUpdate,
  onProgress,
  onConnectionStatus,
  onThinkingStart,
  onThinkingChunk,
  onThinkingEnd,
  onError,
  onRunStatus,
  onRunView,
  resumeRun,
  onComplete
}: ChatWithBackendOptions) => {
  const config = (useApiStore.getState().config as any)[provider];

  if (!resumeRun && (!config || !config.apiKey)) {
    throw new Error(`请先在设置中填写 ${provider} 的 API Key`);
  }

  const controller = new AbortController();
  const signalSource = abortSignal || controller.signal;
  const timeoutMs = 120_000;
  let timeoutId: ReturnType<typeof setTimeout> | null = null;

  if (onConnectionStatus) onConnectionStatus('connecting');

  let currentRunId: string | null = resumeRun?.runId || null;
  let lastSequence = resumeRun?.after || 0;
  let durableRun: boolean | null = resumeRun?.durable ?? null;
  let explicitNonDurableCompletion = false;
  const seenSequences = new Set<number>();
  let terminalStatus: {
    run_id: string;
    status: TerminalStatus;
    error_code?: string | null;
    last_sequence?: number;
  } | null = null;
  let replayAfterDisconnect: (() => Promise<boolean>) | null = null;
  let runView: RunView = {
    runId: currentRunId,
    lastSequence,
    durable: durableRun,
    phase: 'thinking',
    terminalStatus: null,
    connectionStatus: 'connecting',
    cancelling: false,
  };
  const emitRunView = (updates: Partial<RunView> = {}) => {
    runView = {
      ...runView,
      ...updates,
      runId: currentRunId,
      lastSequence,
      durable: durableRun,
    };
    if (onRunView) onRunView(runView);
  };
  const getTerminalStatus = (): TerminalStatus | null => terminalStatus?.status || null;

  try {
    const userToken = localStorage.getItem('token');
    const response = await fetch(
      resumeRun
        ? `/api/v1/runs/${encodeURIComponent(resumeRun.runId)}/events?after=${resumeRun.after || 0}`
        : '/api/v1/chat',
      {
        method: resumeRun ? 'GET' : 'POST',
        signal: signalSource,
        headers: resumeRun
          ? (userToken ? { Authorization: `Bearer ${userToken}` } : {})
          : {
              'Content-Type': 'application/json',
              'X-Api-Key': config.apiKey,
              'X-Provider-Endpoint': config.endpoint || '',
              ...(userToken ? { Authorization: `Bearer ${userToken}` } : {}),
            },
        ...(resumeRun ? {} : {
          body: JSON.stringify({
            messages,
            model,
            temperature,
            prompt_config,
            thread_id,
            deepseek_options: provider === 'deepseek'
              ? {
                  thinking: config.thinking ?? true,
                  reasoning_effort: config.reasoningEffort ?? 'high',
                } satisfies DeepSeekOptions
              : undefined,
          }),
        }),
      },
    );

    if (!response.ok) {
      if (response.status === 401) invalidateAuth();
      throw new Error(`API request failed: ${response.status}`);
    }

    if (!resumeRun && !response.body) {
      throw new Error('No response body');
    }

    if (onConnectionStatus) onConnectionStatus('connected');
    emitRunView({ connectionStatus: 'connected' });
    // Per-event logging is intentionally opt-in; console I/O can dominate
    // the main thread while a model emits many small SSE frames.
    const streamDebug = process.env.NEXT_PUBLIC_CHAT_STREAM_DEBUG === '1';
    const handleFrame = (frame: ParsedSSEEvent) => {
      const data = frame.data;
      if (typeof data.run_id === 'string') currentRunId = data.run_id;
      if (durableRun === null && typeof data.durable === 'boolean') {
        durableRun = data.durable;
      }
      const frameSequence = maxSequence(
        frame.id,
        data.sequence,
        data.stream_sequence,
        data.last_sequence,
      );
      if (frameSequence !== null) {
        if (frameSequence <= lastSequence || seenSequences.has(frameSequence)) return;
        seenSequences.add(frameSequence);
        lastSequence = frameSequence;
      }

      const normalizedTerminal = normalizeTerminalStatus(frame.type, data);
      if (normalizedTerminal) {
        const status = {
          run_id: currentRunId || String(data.run_id || ''),
          status: normalizedTerminal.status,
          error_code: normalizedTerminal.error_code,
          last_sequence: maxSequence(data.last_sequence, lastSequence) || 0,
        };
        currentRunId = status.run_id || currentRunId;
        lastSequence = Math.max(lastSequence, status.last_sequence || 0);
        if (!terminalStatus) {
          terminalStatus = status;
          if (onRunStatus) onRunStatus(status);
          emitRunView({
            phase: phaseForTerminalStatus(normalizedTerminal.status),
            terminalStatus: normalizedTerminal.status,
            errorCode: normalizedTerminal.error_code,
            cancelling: false,
          });
        }
        return;
      }

      const nextPhase = phaseForEvent(frame.type);
      if (frame.type === 'run.cancel_requested') {
        emitRunView({ cancelling: true });
      }

      switch (frame.type) {
        case 'message_chunk':
          if (typeof data.content === 'string' && data.content && onMessageChunk) {
            onMessageChunk(data.content);
          }
          break;
        case 'message_start':
          if (onMessageStart) onMessageStart();
          break;
        case 'message_end':
          explicitNonDurableCompletion = true;
          if (onMessageEnd) onMessageEnd();
          break;
        case 'thinking_start':
          if (onThinkingStart) onThinkingStart();
          break;
        case 'thinking_chunk':
          if (typeof data.content === 'string' && data.content && onThinkingChunk) {
            onThinkingChunk(data.content);
          }
          break;
        case 'thinking_end':
          if (onThinkingEnd) onThinkingEnd();
          break;
        case 'tool_call_delta':
          {
            const invocationId = stringValue(data.invocation_id) || stringValue(data.id);
            const capability = stringValue(data.capability) || stringValue(data.name);
            if (onToolCallDelta && invocationId && capability && typeof data.delta === 'string') {
              onToolCallDelta(invocationId, capability, data.delta);
            }
          }
          break;
        case 'tool_call_start':
          {
            const invocationId = stringValue(data.invocation_id) || stringValue(data.id);
            const capability = stringValue(data.capability) || stringValue(data.name);
            if (onToolCallStart && invocationId && capability) {
              onToolCallStart(
                invocationId,
                capability,
                normalizeArgumentKeys(data.argument_keys ?? data.inputs),
              );
            }
          }
          break;
        case 'tool_call_end':
          {
            const invocationId = stringValue(data.invocation_id) || stringValue(data.id);
            const capability = stringValue(data.capability) || stringValue(data.name);
            if (onToolCallEnd && invocationId && capability) {
              onToolCallEnd(
                invocationId,
                capability,
                data.output,
                optionalNumberValue(data.duration_ms),
                normalizeInvocationStatus(data.status, data.error_code),
                typeof data.error_code === 'string' ? data.error_code : null,
              );
            }
          }
          break;
        case 'plan_update':
          if (typeof data.content === 'string' && data.content && onPlanUpdate) {
            onPlanUpdate(data.content);
          }
          break;
        case 'progress':
          if (onProgress && typeof data.tool_name === 'string' && data.tool_name) {
            onProgress({
              tool_name: data.tool_name,
              tool_count: numberValue(data.tool_count, 1),
              duration_ms: numberValue(data.duration_ms),
            });
          }
          break;
        case 'reasoning_chunk':
          if (typeof data.content === 'string' && data.content && onThinkingChunk) {
            onThinkingChunk(data.content);
          }
          break;
        case 'tool_start':
          {
            const name = stringValue(data.name);
            if (name && onToolCallStart) {
              onToolCallStart(stringValue(data.id) || name, name, data.inputs);
            }
          }
          break;
        case 'tool_end':
          {
            const name = stringValue(data.name);
            if (name && onToolCallEnd) {
              onToolCallEnd(
                stringValue(data.id) || name,
                name,
                data.output,
                optionalNumberValue(data.duration_ms),
                stringValue(data.status) || 'success',
              );
            }
          }
          break;
        case 'error':
          if (typeof data.detail === 'string' && data.detail && onError) {
            onError(
              data.detail,
              typeof data.error_code === 'string' ? data.error_code : null,
            );
          }
          break;
      }
      emitRunView(nextPhase ? { phase: nextPhase } : {});
    };

    replayAfterDisconnect = async (): Promise<boolean> => {
      if (!currentRunId) return false;
      const replayToken = localStorage.getItem('token');
      while (!terminalStatus) {
        const cursorBeforeRequest = lastSequence;
        const replayResponse = await fetch(
          `/api/v1/runs/${encodeURIComponent(currentRunId)}/events?after=${lastSequence}`,
          {
            method: 'GET',
            signal: signalSource,
            headers: replayToken ? { Authorization: `Bearer ${replayToken}` } : {},
          },
        );
        if (!replayResponse.ok) {
          throw new Error(`Replay request failed: ${replayResponse.status}`);
        }
        const replayPayload = await replayResponse.json();
        const persistedEvents = Array.isArray(replayPayload.events)
          ? replayPayload.events
          : [];
        for (const persistedEvent of persistedEvents) {
          const payload = persistedEvent.payload && typeof persistedEvent.payload === 'object'
            ? persistedEvent.payload
            : {};
          handleFrame({
            type: persistedEvent.event_type,
            id: String(persistedEvent.sequence),
            data: {
              ...payload,
              run_id: persistedEvent.run_id,
              sequence: persistedEvent.sequence,
            },
          });
        }
        if (
          terminalStatus ||
          persistedEvents.length < 500 ||
          lastSequence <= cursorBeforeRequest
        ) {
          break;
        }
      }
      return terminalStatus !== null;
    };

    const notifyComplete = () => {
      if (onComplete) {
        onComplete({
          hasDurableRun: durableRun === true,
          terminalStatus: getTerminalStatus(),
        });
      }
    };

    if (resumeRun) {
      const replayPayload = await response.json();
      const persistedEvents = Array.isArray(replayPayload.events)
        ? replayPayload.events
        : [];
      for (const persistedEvent of persistedEvents) {
        const payload = persistedEvent.payload && typeof persistedEvent.payload === 'object'
          ? persistedEvent.payload
          : {};
        handleFrame({
          type: persistedEvent.event_type,
          id: String(persistedEvent.sequence),
          data: {
            ...payload,
            run_id: persistedEvent.run_id || resumeRun.runId,
            sequence: persistedEvent.sequence,
          },
        });
      }
      if (terminalStatus) {
        notifyComplete();
      } else if (onError) {
        onError('Replay ended before a terminal run event');
      }
      return;
    }

    const finishAfterStreamEnd = async () => {
      if (terminalStatus) {
        notifyComplete();
        return;
      }

      if (durableRun === true && replayAfterDisconnect) {
        const replayed = await replayAfterDisconnect();
        if (replayed) {
          notifyComplete();
          return;
        }
      }

      const hasLegacyEphemeralCompletion = (
        durableRun === false || (durableRun === null && currentRunId === null)
      );
      if (hasLegacyEphemeralCompletion && explicitNonDurableCompletion) {
        notifyComplete();
        return;
      }

      if (onError) onError('运行流结束但未收到终态事件');
    };

    const resetTimeout = () => {
      if (timeoutId) clearTimeout(timeoutId);
      timeoutId = setTimeout(() => {
        reader.cancel().catch(() => {});
        if (onError) onError('请求超时');
      }, timeoutMs);
    };

    const reader = response.body!.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    resetTimeout();

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      resetTimeout();
      buffer += decoder.decode(value, { stream: true });

      let eventEndIndex;
      while ((eventEndIndex = buffer.indexOf('\n\n')) !== -1) {
        const chunkToParse = buffer.slice(0, eventEndIndex + 2);
        buffer = buffer.slice(eventEndIndex + 2);
        const events = parseSSE(chunkToParse);

        for (const event of events) {
          if (streamDebug) {
            console.debug('[chat-stream] ' + JSON.stringify({
              type: event.type,
              sequence: event.data.stream_sequence,
              serverElapsedMs: event.data.server_elapsed_ms,
              receivedAtMs: Math.round(performance.now()),
              contentLength: typeof event.data.content === 'string' ? event.data.content.length : 0,
            }));
          }
          handleFrame(event);
        }
      }
    }

    await finishAfterStreamEnd();
  } catch (err: any) {
    if (err?.name === 'AbortError') {
      // A user-initiated stop is a normal terminal state. Keep any streamed
      // content instead of replacing it with an error message.
    } else {
      let replayed = false;
      if (durableRun === true && !terminalStatus && replayAfterDisconnect) {
        try {
          replayed = await replayAfterDisconnect();
        } catch (replayError: any) {
          err = replayError;
        }
      }
      if (replayed) {
        if (onComplete) {
          onComplete({
            hasDurableRun: durableRun === true,
            terminalStatus: getTerminalStatus(),
          });
        }
      } else if (terminalStatus) {
        if (onComplete) {
          onComplete({
            hasDurableRun: durableRun === true,
            terminalStatus: getTerminalStatus(),
          });
        }
      } else if (onError) {
        onError(err?.message || String(err));
      }
    }
  } finally {
    if (timeoutId) clearTimeout(timeoutId);
    if (onConnectionStatus) onConnectionStatus('disconnected');
  }
};

export const fetchChatHistory = async (threadId: string, signal?: AbortSignal): Promise<any[]> => {
  const normalizedThreadId = typeof threadId === 'string' ? threadId.trim() : '';
  if (!normalizedThreadId || normalizedThreadId === '[object Object]') {
    throw new Error('Invalid chat thread id');
  }
  const token = localStorage.getItem("token");
  const response = await fetch(
    `/api/v1/chat/history?thread_id=${encodeURIComponent(normalizedThreadId)}`,
    {
      signal,
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    }
  );
  if (!response.ok) {
    if (response.status === 401) invalidateAuth();
    throw new Error(`Chat history request failed: ${response.status}`);
  }
  const data = await response.json();
  return data.messages || [];
};

export const fetchCurrentUser = async (): Promise<CurrentUser | null> => {
  const token = localStorage.getItem('token');
  if (!token) return null;
  const response = await fetch('/api/v1/users/me', {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (response.status === 401) {
    invalidateAuth();
    return null;
  }
  if (!response.ok) {
    throw new Error(`User request failed: ${response.status}`);
  }
  return response.json();
};

export const cancelRun = async (runId: string, threadId?: string): Promise<Record<string, unknown>> => {
  const token = localStorage.getItem('token');
  const query = threadId ? `?thread_id=${encodeURIComponent(threadId)}` : '';
  const response = await fetch(
    `/api/v1/runs/${encodeURIComponent(runId)}/cancel${query}`,
    {
      method: 'POST',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    },
  );
  if (!response.ok) {
    throw new Error(`Cancel request failed: ${response.status}`);
  }
  return response.json();
};

export const deleteChatHistory = async (threadId: string): Promise<void> => {
  const token = localStorage.getItem("token");
  await fetch(
    `/api/v1/chat/history/${encodeURIComponent(threadId)}`,
    {
      method: 'DELETE',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    }
  );
};

export const listThreads = async (xApiKey?: string, xBaseUrl?: string): Promise<string[]> => {
  const token = localStorage.getItem("token");
  const params = new URLSearchParams();
  if (xApiKey) params.set('x_api_key', xApiKey);
  if (xBaseUrl) params.set('x_base_url', xBaseUrl);
  const response = await fetch(
    `/api/v1/chat/threads?${params.toString()}`,
    {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    }
  );
  if (!response.ok) {
    if (response.status === 401) invalidateAuth();
    throw new Error(`Chat threads request failed: ${response.status}`);
  }
  const data = await response.json();
  const rawThreads: unknown = data && typeof data === 'object' ? data.threads : undefined;
  if (!Array.isArray(rawThreads)) return [];

  const threadIds = rawThreads.map((thread): string | null => {
    if (typeof thread === 'string') {
      const value = thread.trim();
      return value && value !== '[object Object]' ? value : null;
    }
    if (!thread || typeof thread !== 'object') return null;
    const record = thread as Record<string, unknown>;
    for (const key of ['thread_id', 'public_id', 'threadId', 'publicThreadId', 'id']) {
      const value = record[key];
      if (typeof value === 'string' && value.trim() && value !== '[object Object]') {
        return value.trim();
      }
    }
    return null;
  }).filter((threadId): threadId is string => threadId !== null);

  return [...new Set(threadIds)];
};
