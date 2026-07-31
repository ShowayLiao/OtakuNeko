/* eslint-disable @typescript-eslint/no-explicit-any -- SSE payloads are provider-defined JSON. */
import { useApiStore } from '@/store/useApiStore';

interface PromptConfig {
  persona: string;
  tone: string;
  rules: string;
}

interface DeepSeekOptions {
  thinking: boolean;
  reasoning_effort: 'high' | 'max';
}

type SSEData = Record<string, any>;

interface ParsedSSEEvent {
  type: string;
  data: SSEData;
  id?: string;
}

interface ChatWithBackendOptions {
  messages: any[];
  provider: string;
  model?: string;
  temperature?: number;
  prompt_config?: PromptConfig;
  thread_id?: string;
  abortSignal?: AbortSignal;
  onMessageChunk?: (chunk: string) => void;
  onMessageStart?: () => void;
  onMessageEnd?: () => void;
  onToolCallStart?: (id: string, name: string, inputs: any) => void;
  onToolCallEnd?: (id: string, name: string, output: any, durationMs?: number, status?: string) => void;
  onToolCallDelta?: (id: string, name: string, delta: string) => void;
  onPlanUpdate?: (plan: string) => void;
  onProgress?: (data: { tool_name: string; tool_count: number; duration_ms: number }) => void;
  onConnectionStatus?: (status: 'connected' | 'connecting' | 'disconnected') => void;
  onThinkingStart?: () => void;
  onThinkingChunk?: (chunk: string) => void;
  onThinkingEnd?: () => void;
  onError?: (error: string) => void;
  onRunStatus?: (status: {
    run_id: string;
    status: string;
    error_code?: string | null;
    last_sequence?: number;
  }) => void;
  onComplete?: (metadata?: {
    hasDurableRun: boolean;
    terminalStatus: string | null;
  }) => void;
}

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
        } catch (e) {
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
  onComplete
}: ChatWithBackendOptions) => {
  const config = (useApiStore.getState().config as any)[provider];

  if (!config || !config.apiKey) {
    throw new Error(`请先在设置中填写 ${provider} 的 API Key`);
  }

  const controller = new AbortController();
  const signalSource = abortSignal || controller.signal;
  const timeoutMs = 120_000;
  let timeoutId: ReturnType<typeof setTimeout> | null = null;

  if (onConnectionStatus) onConnectionStatus('connecting');

  let currentRunId: string | null = null;
  let lastSequence = 0;
  let terminalStatus: {
    run_id: string;
    status: string;
    error_code?: string | null;
    last_sequence?: number;
  } | null = null;
  let replayAfterDisconnect: (() => Promise<boolean>) | null = null;
  const getTerminalStatus = () =>
    (terminalStatus as { status: string } | null)?.status || null;

  try {
    const userToken = localStorage.getItem('token');
    const response = await fetch('/api/v1/chat', {
      method: 'POST',
      signal: signalSource,
      headers: {
        'Content-Type': 'application/json',
        'X-Api-Key': config.apiKey,
        'X-Provider-Endpoint': config.endpoint || '',
        ...(userToken ? { Authorization: `Bearer ${userToken}` } : {}),
      },
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
    });

    if (!response.ok) {
      throw new Error(`API request failed: ${response.status}`);
    }

    if (!response.body) {
      throw new Error('No response body');
    }

    if (onConnectionStatus) onConnectionStatus('connected');

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    // Per-event logging is intentionally opt-in; console I/O can dominate
    // the main thread while a model emits many small SSE frames.
    const streamDebug = process.env.NEXT_PUBLIC_CHAT_STREAM_DEBUG === '1';
    const handleFrame = (frame: ParsedSSEEvent) => {
      const data = frame.data;
      if (typeof data.run_id === 'string') currentRunId = data.run_id;
      const frameSequence = Number(frame.id ?? data.sequence ?? data.stream_sequence);
      if (Number.isFinite(frameSequence)) {
        lastSequence = Math.max(lastSequence, frameSequence);
      }

      const statusFromEvent = frame.type === 'run_status'
        ? data.status
        : frame.type === 'run.succeeded'
          ? 'succeeded'
          : frame.type === 'run.failed'
            ? 'failed'
            : frame.type === 'run.cancelled'
              ? 'cancelled'
              : undefined;
      if (typeof statusFromEvent === 'string' &&
        ['succeeded', 'failed', 'cancelled'].includes(statusFromEvent)) {
        const status = {
          run_id: currentRunId || String(data.run_id || ''),
          status: statusFromEvent,
          error_code: data.error_code ?? null,
          last_sequence: Number(data.last_sequence ?? lastSequence),
        };
        currentRunId = status.run_id || currentRunId;
        lastSequence = Math.max(lastSequence, status.last_sequence || 0);
        if (!terminalStatus) {
          terminalStatus = status;
          if (onRunStatus) onRunStatus(status);
        }
        return;
      }

      switch (frame.type) {
        case 'message_chunk':
          if (data.content && onMessageChunk) onMessageChunk(data.content);
          break;
        case 'message_start':
          if (onMessageStart) onMessageStart();
          break;
        case 'message_end':
          if (onMessageEnd) onMessageEnd();
          break;
        case 'thinking_start':
          if (onThinkingStart) onThinkingStart();
          break;
        case 'thinking_chunk':
          if (data.content && onThinkingChunk) onThinkingChunk(data.content);
          break;
        case 'thinking_end':
          if (onThinkingEnd) onThinkingEnd();
          break;
        case 'tool_call_delta':
          if (onToolCallDelta && data.id) onToolCallDelta(data.id, data.name, data.delta);
          break;
        case 'tool_call_start':
          if (data.name && onToolCallStart) {
            onToolCallStart(data.id || data.name, data.name, data.inputs || data.argument_keys);
          }
          break;
        case 'tool_call_end':
          if (data.name && onToolCallEnd) {
            onToolCallEnd(
              data.id || data.name,
              data.name,
              data.output,
              data.duration_ms,
              data.status,
            );
          }
          break;
        case 'plan_update':
          if (data.content && onPlanUpdate) onPlanUpdate(data.content);
          break;
        case 'progress':
          if (onProgress && data.tool_name) {
            onProgress({
              tool_name: data.tool_name,
              tool_count: data.tool_count || 1,
              duration_ms: data.duration_ms || 0,
            });
          }
          break;
        case 'reasoning_chunk':
          if (data.content && onThinkingChunk) onThinkingChunk(data.content);
          break;
        case 'tool_start':
          if (data.name && onToolCallStart) {
            onToolCallStart(data.id || data.name, data.name, data.inputs);
          }
          break;
        case 'tool_end':
          if (data.name && onToolCallEnd) {
            onToolCallEnd(
              data.id || data.name,
              data.name,
              data.output,
              data.duration_ms,
              data.status || 'success',
            );
          }
          break;
        case 'error':
          if (data.detail && onError) onError(data.detail);
          break;
      }
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

    const resetTimeout = () => {
      if (timeoutId) clearTimeout(timeoutId);
      timeoutId = setTimeout(() => {
        reader.cancel().catch(() => {});
        if (onError) onError('请求超时');
      }, timeoutMs);
    };

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

    if (onComplete) {
      onComplete({
        hasDurableRun: currentRunId !== null,
        terminalStatus: getTerminalStatus(),
      });
    }
  } catch (err: any) {
    if (err?.name === 'AbortError') {
      // A user-initiated stop is a normal terminal state. Keep any streamed
      // content instead of replacing it with an error message.
    } else {
      let replayed = false;
      if (currentRunId && !terminalStatus && replayAfterDisconnect) {
        try {
          replayed = await replayAfterDisconnect();
        } catch (replayError: any) {
          err = replayError;
        }
      }
      if (replayed) {
        if (onComplete) {
          onComplete({
            hasDurableRun: currentRunId !== null,
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
  const token = localStorage.getItem("token");
  const response = await fetch(
    `/api/v1/chat/history?thread_id=${encodeURIComponent(threadId)}`,
    {
      signal,
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    }
  );
  if (!response.ok) return [];
  const data = await response.json();
  return data.messages || [];
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
  if (!response.ok) return [];
  const data = await response.json();
  return data.threads || [];
};
