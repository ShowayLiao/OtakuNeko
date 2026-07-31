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
  onComplete?: () => void;
}

// 解析 SSE 事件流
const parseSSE = (text: string): ParsedSSEEvent[] => {
  const events: ParsedSSEEvent[] = [];
  const lines = text.split('\n');
  let event: { type: string; data: string } = { type: 'message', data: '' };
  
  for (const line of lines) {
    if (line.startsWith('event:')) {
      event.type = line.substring(6).trim();
    } else if (line.startsWith('data:')) {
      event.data += line.substring(5).trim() + '\n';
    } else if (line === '') {
      if (event.data) {
        try {
          const data = JSON.parse(event.data.trim());
          if (typeof data === 'object' && data !== null) {
            events.push({ type: event.type, data: data as SSEData });
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

    const resetTimeout = () => {
      if (timeoutId) clearTimeout(timeoutId);
      timeoutId = setTimeout(() => {
        reader.cancel().catch(() => {});
        if (onError) onError('请求超时');
        if (onComplete) onComplete();
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
          switch (event.type) {
            case 'message_chunk':
              if (event.data.content && onMessageChunk) {
                onMessageChunk(event.data.content);
              }
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
              if (event.data.content && onThinkingChunk) {
                onThinkingChunk(event.data.content);
              }
              break;
            case 'thinking_end':
              if (onThinkingEnd) onThinkingEnd();
              break;
            case 'tool_call_delta':
              if (onToolCallDelta && event.data.id) {
                onToolCallDelta(event.data.id, event.data.name, event.data.delta);
              }
              break;
            case 'tool_call_start':
              if (event.data.name && onToolCallStart) {
                onToolCallStart(event.data.id || event.data.name, event.data.name, event.data.inputs);
              }
              break;
            case 'tool_call_end':
              if (event.data.name && onToolCallEnd) {
                onToolCallEnd(
                  event.data.id || event.data.name,
                  event.data.name,
                  event.data.output,
                  event.data.duration_ms,
                  event.data.status
                );
              }
              break;
            case 'plan_update':
              if (event.data.content && onPlanUpdate) {
                onPlanUpdate(event.data.content);
              }
              break;
            case 'progress':
              if (onProgress && event.data.tool_name) {
                onProgress({
                  tool_name: event.data.tool_name,
                  tool_count: event.data.tool_count || 1,
                  duration_ms: event.data.duration_ms || 0,
                });
              }
              break;
            case 'reasoning_chunk':
              if (event.data.content && onThinkingChunk) {
                onThinkingChunk(event.data.content);
              }
              break;
            case 'tool_start':
              if (event.data.name && onToolCallStart) {
                onToolCallStart(event.data.id || event.data.name, event.data.name, event.data.inputs);
              }
              break;
            case 'tool_end':
              if (event.data.name && onToolCallEnd) {
                onToolCallEnd(
                  event.data.id || event.data.name,
                  event.data.name,
                  event.data.output,
                  event.data.duration_ms,
                  event.data.status || 'success'
                );
              }
              break;
            case 'error':
              if (event.data.detail && onError) {
                onError(event.data.detail);
              }
              break;
          }
        }
      }
    }

    if (onComplete) {
      onComplete();
    }
  } catch (err: any) {
    if (err?.name === 'AbortError') {
      // A user-initiated stop is a normal terminal state. Keep any streamed
      // content instead of replacing it with an error message.
    } else if (onError) {
      onError(err?.message || String(err));
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
