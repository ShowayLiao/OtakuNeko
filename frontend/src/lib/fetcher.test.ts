import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  cancelRun,
  chatWithBackend,
  fetchChatHistory,
  fetchCurrentUser,
  listThreads,
} from './fetcher';

vi.mock('@/store/useApiStore', () => ({
  useApiStore: {
    getState: () => ({
      config: {
        deepseek: {
          apiKey: 'provider-key',
          endpoint: 'http://provider.test',
        },
      },
    }),
  },
}));

describe('chatWithBackend authentication', () => {
  afterEach(() => {
    localStorage.clear();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('requests durable cancellation without aborting or resubmitting chat', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ run_id: 'run-cancel', cancellation_requested: true }),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    ));
    vi.stubGlobal('fetch', fetchMock);
    localStorage.setItem('token', 'user-access-token');

    await expect(cancelRun('run-cancel', 'thread-1')).resolves.toEqual({
      run_id: 'run-cancel',
      cancellation_requested: true,
    });

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/runs/run-cancel/cancel?thread_id=thread-1',
      expect.objectContaining({
        method: 'POST',
        headers: { Authorization: 'Bearer user-access-token' },
      }),
    );
  });

  it('forwards the logged-in user token to the chat request', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    localStorage.setItem('token', 'user-access-token');

    await chatWithBackend({
      messages: [],
      provider: 'deepseek',
    });

    const requestInit = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(new Headers(requestInit.headers).get('authorization')).toBe(
      'Bearer user-access-token',
    );
  });

  it('preserves provider configuration errors from a rejected chat request', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: 'Missing API Key' }),
      { status: 401, headers: { 'Content-Type': 'application/json' } },
    )));
    localStorage.setItem('token', 'user-access-token');
    const onError = vi.fn();

    await chatWithBackend({
      messages: [],
      provider: 'deepseek',
      onError,
    });
    expect(onError).toHaveBeenCalledWith('Missing API Key', 'configuration_error');
    expect(localStorage.getItem('token')).toBe('user-access-token');
  });

  it('invalidates an expired user token rejected by the chat endpoint', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: 'Invalid authentication credentials' }),
      {
        status: 401,
        headers: {
          'Content-Type': 'application/json',
          'WWW-Authenticate': 'Bearer',
        },
      },
    )));
    localStorage.setItem('token', 'expired-token');
    const onError = vi.fn();

    await chatWithBackend({
      messages: [],
      provider: 'deepseek',
      onError,
    });

    expect(onError).toHaveBeenCalledWith(
      'Invalid authentication credentials',
      'authentication_error',
    );
    expect(localStorage.getItem('token')).toBeNull();
  });

  it('surfaces authentication failures when loading chat history', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: 'unauthorized' }), { status: 401 }),
    ));
    localStorage.setItem('token', 'expired-token');

    await expect(fetchChatHistory('thread-1')).rejects.toThrow(
      'Chat history request failed: 401',
    );
    expect(localStorage.getItem('token')).toBeNull();
  });

  it('rejects an invalid thread id before making a malformed history request', async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    await expect(fetchChatHistory({} as unknown as string)).rejects.toThrow(
      'Invalid chat thread id',
    );
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('loads the authenticated user through the same frontend proxy', async () => {
    localStorage.setItem('token', 'user-access-token');
    const fetchMock = vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ id: 7, username: 'user-7' }),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    ));
    vi.stubGlobal('fetch', fetchMock);

    await expect(fetchCurrentUser()).resolves.toMatchObject({ id: 7, username: 'user-7' });
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/users/me',
      { headers: { Authorization: 'Bearer user-access-token' } },
    );
  });

  it('does not convert an unauthorized thread list into an empty account', async () => {
    localStorage.setItem('token', 'expired-token');
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 401 })));

    await expect(listThreads()).rejects.toThrow('Chat threads request failed: 401');
    expect(localStorage.getItem('token')).toBeNull();
  });

  it('normalizes legacy thread records before they become URL parameters', async () => {
    localStorage.setItem('token', 'user-access-token');
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      JSON.stringify({
        threads: [
          { thread_id: 'thread-1' },
          { id: 'thread-2' },
          { public_id: 'thread-3' },
          { unsupported: 'must-be-ignored' },
          'thread-1',
        ],
      }),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    )));

    await expect(listThreads()).resolves.toEqual(['thread-1', 'thread-2', 'thread-3']);
  });

  it('replays the current SSE event vocabulary into callbacks', async () => {
    const frames = [
      ['thinking_start', { stream_sequence: 1 }],
      ['tool_start', { stream_sequence: 2, id: 'tool-1', name: 'fake.search', inputs: {} }],
      ['tool_end', { stream_sequence: 3, id: 'tool-1', name: 'fake.search', output: { success: true }, status: 'success' }],
      ['message_start', { stream_sequence: 4 }],
      ['message_chunk', { stream_sequence: 5, content: 'answer' }],
      ['message_end', { stream_sequence: 6 }],
    ]
      .map(([type, data]) => `event: ${type}\ndata: ${JSON.stringify(data)}\n\n`)
      .join('');
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(frames));
        controller.close();
      },
    });
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(body, { status: 200, headers: { 'Content-Type': 'text/event-stream' } }),
    );
    vi.stubGlobal('fetch', fetchMock);
    const events: string[] = [];

    await chatWithBackend({
      messages: [],
      provider: 'deepseek',
      onThinkingStart: () => events.push('thinking_start'),
      onToolCallStart: (_id, name) => events.push(`tool_start:${name}`),
      onToolCallEnd: (_id, name, _output, _duration, status) => events.push(`tool_end:${name}:${status}`),
      onMessageStart: () => events.push('message_start'),
      onMessageChunk: chunk => events.push(`message_chunk:${chunk}`),
      onMessageEnd: () => events.push('message_end'),
      onComplete: () => events.push('complete'),
    });

    expect(events).toEqual([
      'thinking_start',
      'tool_start:fake.search',
      'tool_end:fake.search:success',
      'message_start',
      'message_chunk:answer',
      'message_end',
      'complete',
    ]);
  });

  it('normalizes primary invocation fields without creating a process from model_decision', async () => {
    const frames = [
      ['model_decision', {
        run_id: 'run-invocation',
        durable: true,
        sequence: 1,
        action: 'invoke',
        capability: 'library.search',
        argument_keys: ['query', 'limit'],
      }],
      ['tool_call_start', {
        run_id: 'run-invocation',
        durable: true,
        sequence: 2,
        invocation_id: 'inv-1',
        capability: 'library.search',
        argument_keys: ['query', 'limit'],
        inputs: { query: 'secret value', limit: 5 },
      }],
      ['tool_call_end', {
        run_id: 'run-invocation',
        durable: true,
        sequence: 3,
        invocation_id: 'inv-1',
        capability: 'library.search',
        status: 'denied',
        error_code: 'permission_denied',
        output: { safe: true },
      }],
      ['run_completed', { run_id: 'run-invocation', durable: true, sequence: 4 }],
    ]
      .map(([type, data]) => `event: ${type}\ndata: ${JSON.stringify(data)}\n\n`)
      .join('');
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(frames));
        controller.close();
      },
    });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response(body, { status: 200, headers: { 'Content-Type': 'text/event-stream' } }),
    ));
    const starts: unknown[] = [];
    const ends: unknown[] = [];

    await chatWithBackend({
      messages: [],
      provider: 'deepseek',
      onToolCallStart: (...args) => starts.push(args),
      onToolCallEnd: (...args) => ends.push(args),
    });

    expect(starts).toEqual([['inv-1', 'library.search', ['query', 'limit']]]);
    expect(ends).toEqual([[
      'inv-1',
      'library.search',
      { safe: true },
      undefined,
      'denied',
      'permission_denied',
    ]]);
  });

  it('replays a durable run through GET without resubmitting the chat request', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(
      JSON.stringify({
        events: [
          {
            event_id: 'evt-thinking',
            run_id: 'run-refresh',
            sequence: 3,
            event_type: 'thinking_start',
            payload: {},
          },
          {
            event_id: 'evt-answer',
            run_id: 'run-refresh',
            sequence: 4,
            event_type: 'message_chunk',
            payload: { content: 'partial answer' },
          },
          {
            event_id: 'evt-failed',
            run_id: 'run-refresh',
            sequence: 5,
            event_type: 'run.failed',
            payload: { error_code: 'provider_error' },
          },
        ],
      }),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    ));
    vi.stubGlobal('fetch', fetchMock);
    const views: Array<{ phase: string; lastSequence: number; terminalStatus: string | null }> = [];
    const chunks: string[] = [];
    const completions: unknown[] = [];
    const errors: string[] = [];

    await chatWithBackend({
      messages: [],
      provider: 'deepseek',
      resumeRun: { runId: 'run-refresh', after: 2, durable: true },
      onRunView: view => views.push({
        phase: view.phase,
        lastSequence: view.lastSequence,
        terminalStatus: view.terminalStatus,
      }),
      onMessageChunk: chunk => chunks.push(chunk),
      onComplete: metadata => completions.push(metadata),
      onError: error => errors.push(error),
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/runs/run-refresh/events?after=2');
    expect((fetchMock.mock.calls[0]?.[1] as RequestInit).method).toBe('GET');
    expect(chunks).toEqual(['partial answer']);
    expect(views.at(-1)).toEqual({ phase: 'failed', lastSequence: 5, terminalStatus: 'failed' });
    expect(completions).toEqual([{ hasDurableRun: true, terminalStatus: 'failed' }]);
    expect(errors).toEqual([]);
  });

  it('ignores replay events at or before the resume cursor', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(
      JSON.stringify({
        events: [
          {
            event_id: 'evt-duplicate',
            run_id: 'run-stale-replay',
            sequence: 2,
            event_type: 'message_chunk',
            payload: { content: 'duplicate' },
          },
          {
            event_id: 'evt-new',
            run_id: 'run-stale-replay',
            sequence: 3,
            event_type: 'message_chunk',
            payload: { content: 'new' },
          },
          {
            event_id: 'evt-failed',
            run_id: 'run-stale-replay',
            sequence: 4,
            event_type: 'run.failed',
            payload: { error_code: 'provider_error' },
          },
        ],
      }),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    ));
    vi.stubGlobal('fetch', fetchMock);
    const chunks: string[] = [];

    await chatWithBackend({
      messages: [],
      provider: 'deepseek',
      resumeRun: { runId: 'run-stale-replay', after: 2, durable: true },
      onMessageChunk: chunk => chunks.push(chunk),
    });

    expect(chunks).toEqual(['new']);
  });

  it('does not treat a replay response without a terminal event as success', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      JSON.stringify({
        events: [{
          event_id: 'evt-thinking',
          run_id: 'run-incomplete',
          sequence: 2,
          event_type: 'thinking_start',
          payload: {},
        }],
      }),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    )));
    const completions: unknown[] = [];
    const errors: string[] = [];

    await chatWithBackend({
      messages: [],
      provider: 'deepseek',
      resumeRun: { runId: 'run-incomplete', after: 1, durable: true },
      onComplete: metadata => completions.push(metadata),
      onError: error => errors.push(error),
    });

    expect(completions).toEqual([]);
    expect(errors).toHaveLength(1);
  });

  it.each([
    ['run_completed', 'succeeded'],
    ['run_failed', 'failed'],
    ['run_cancelled', 'cancelled'],
    ['run_timeout', 'timeout'],
  ])('normalizes live %s as %s', async (eventType, expectedStatus) => {
    const frames = [
      `event: thinking_start\ndata: ${JSON.stringify({ run_id: 'run-live', durable: true, sequence: 1 })}\n\n`,
      `event: ${eventType}\ndata: ${JSON.stringify({ run_id: 'run-live', durable: true, sequence: 2, error_code: expectedStatus })}\n\n`,
    ].join('');
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(frames));
        controller.close();
      },
    });
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(body, { status: 200, headers: { 'Content-Type': 'text/event-stream' } }),
    );
    vi.stubGlobal('fetch', fetchMock);
    const statuses: string[] = [];
    const completions: Array<{ hasDurableRun: boolean; terminalStatus: string | null }> = [];
    const errors: string[] = [];

    await chatWithBackend({
      messages: [],
      provider: 'deepseek',
      onRunStatus: status => statuses.push(status.status),
      onComplete: metadata => completions.push(metadata!),
      onError: error => errors.push(error),
    });

    expect(statuses).toEqual([expectedStatus]);
    expect(completions).toEqual([{ hasDurableRun: true, terminalStatus: expectedStatus }]);
    expect(errors).toEqual([]);
  });

  it.each([
    ['run.succeeded', 'succeeded'],
    ['run.failed', 'failed'],
    ['run.cancelled', 'cancelled'],
  ])('normalizes replay %s as %s', async (eventType, expectedStatus) => {
    const liveBody = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(
          `id: 1\nevent: thinking_start\ndata: ${JSON.stringify({ run_id: 'run-replay-terminal', durable: true, sequence: 1 })}\n\n`,
        ));
        setTimeout(() => controller.error(new Error('connection lost')), 0);
      },
    });
    const replayResponse = new Response(
      JSON.stringify({
        events: [{
          event_id: `evt-${expectedStatus}`,
          run_id: 'run-replay-terminal',
          sequence: 2,
          event_type: eventType,
          invocation_id: null,
          payload: { error_code: expectedStatus },
        }],
      }),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    );
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(liveBody, {
          status: 200,
          headers: { 'Content-Type': 'text/event-stream' },
        }),
      )
      .mockResolvedValueOnce(replayResponse);
    vi.stubGlobal('fetch', fetchMock);
    const statuses: string[] = [];

    await chatWithBackend({
      messages: [],
      provider: 'deepseek',
      onRunStatus: status => statuses.push(status.status),
    });

    expect(statuses).toEqual([expectedStatus]);
  });

  it.each([
    { status: 'timeout' },
    { error_code: 'timeout' },
  ])('normalizes run.failed timeout marker %# as timeout', async (timeoutMarker) => {
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(
          `event: run.failed\ndata: ${JSON.stringify({ run_id: 'run-timeout', durable: true, sequence: 1, ...timeoutMarker })}\n\n`,
        ));
        controller.close();
      },
    });
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(body, { status: 200, headers: { 'Content-Type': 'text/event-stream' } }),
    );
    vi.stubGlobal('fetch', fetchMock);
    const statuses: string[] = [];

    await chatWithBackend({
      messages: [],
      provider: 'deepseek',
      onRunStatus: status => statuses.push(status.status),
    });

    expect(statuses).toEqual(['timeout']);
  });

  it('normalizes canonical replay run.failed with a timeout marker', async () => {
    const liveBody = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(
          `event: thinking_start\ndata: ${JSON.stringify({ run_id: 'run-replay-timeout', durable: true, sequence: 1 })}\n\n`,
        ));
        setTimeout(() => controller.error(new Error('connection lost')), 0);
      },
    });
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(liveBody, {
          status: 200,
          headers: { 'Content-Type': 'text/event-stream' },
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({
          events: [{
            event_id: 'evt-replay-timeout',
            run_id: 'run-replay-timeout',
            sequence: 2,
            event_type: 'run.failed',
            invocation_id: null,
            payload: { status: 'timeout' },
          }],
        }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      );
    vi.stubGlobal('fetch', fetchMock);
    const statuses: string[] = [];

    await chatWithBackend({
      messages: [],
      provider: 'deepseek',
      onRunStatus: status => statuses.push(status.status),
    });

    expect(statuses).toEqual(['timeout']);
  });

  it('replays durable events after a disconnect without resubmitting the chat POST', async () => {
    const liveFrames = [
      `id: 1\nevent: thinking_start\ndata: ${JSON.stringify({ run_id: 'run-1', durable: true, stream_sequence: 1 })}\n\n`,
      `id: 2\nevent: message_chunk\ndata: ${JSON.stringify({ run_id: 'run-1', durable: true, stream_sequence: 2, content: 'partial' })}\n\n`,
    ].join('');
    const liveBody = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(liveFrames));
        setTimeout(() => controller.error(new Error('connection lost')), 0);
      },
    });
    const replayResponse = new Response(
      JSON.stringify({
        events: [
          {
            event_id: 'evt-3',
            run_id: 'run-1',
            sequence: 3,
            event_type: 'run.succeeded',
            invocation_id: null,
            payload: {},
          },
        ],
      }),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    );
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(liveBody, {
          status: 200,
          headers: { 'Content-Type': 'text/event-stream' },
        }),
      )
      .mockResolvedValueOnce(replayResponse);
    vi.stubGlobal('fetch', fetchMock);
    const statuses: string[] = [];
    const chunks: string[] = [];

    await chatWithBackend({
      messages: [],
      provider: 'deepseek',
      onMessageChunk: chunk => chunks.push(chunk),
      onRunStatus: status => statuses.push(status.status),
    });

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/chat');
    expect(fetchMock.mock.calls[1]?.[0]).toBe(
      '/api/v1/runs/run-1/events?after=2',
    );
    expect(chunks).toEqual(['partial']);
    expect(statuses).toEqual(['succeeded']);
  });

  it('does not replay a run when the stream only carries a non-durable run id', async () => {
    const liveBody = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(
          `id: 1\nevent: thinking_start\ndata: ${JSON.stringify({ run_id: 'run-ephemeral', durable: false, sequence: 1 })}\n\n`,
        ));
        setTimeout(() => controller.error(new Error('connection lost')), 0);
      },
    });
    const fetchMock = vi.fn().mockResolvedValueOnce(
      new Response(liveBody, {
        status: 200,
        headers: { 'Content-Type': 'text/event-stream' },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);
    const errors: string[] = [];

    await chatWithBackend({
      messages: [],
      provider: 'deepseek',
      onError: error => errors.push(error),
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(errors).toEqual(['connection lost']);
  });

  it('uses the maximum valid sequence from event id and payload fields for replay', async () => {
    const liveBody = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(
          `id: 2\nevent: thinking_start\ndata: ${JSON.stringify({ run_id: 'run-sequence', durable: true, sequence: 5, stream_sequence: 8 })}\n\n`,
        ));
        setTimeout(() => controller.error(new Error('connection lost')), 0);
      },
    });
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(liveBody, {
          status: 200,
          headers: { 'Content-Type': 'text/event-stream' },
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ events: [] }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      );
    vi.stubGlobal('fetch', fetchMock);

    await chatWithBackend({ messages: [], provider: 'deepseek' });

    expect(fetchMock.mock.calls[1]?.[0]).toBe(
      '/api/v1/runs/run-sequence/events?after=8',
    );
  });

  it('ignores invalid sequence values without losing a valid payload cursor', async () => {
    const liveBody = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(
          `id: invalid\nevent: thinking_start\ndata: ${JSON.stringify({ run_id: 'run-invalid-sequence', durable: true, sequence: 3 })}\n\n`,
        ));
        setTimeout(() => controller.error(new Error('connection lost')), 0);
      },
    });
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(liveBody, {
          status: 200,
          headers: { 'Content-Type': 'text/event-stream' },
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ events: [] }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      );
    vi.stubGlobal('fetch', fetchMock);

    await chatWithBackend({ messages: [], provider: 'deepseek' });

    expect(fetchMock.mock.calls[1]?.[0]).toBe(
      '/api/v1/runs/run-invalid-sequence/events?after=3',
    );
  });

  it('does not replay duplicate sequence events or duplicate terminal callbacks', async () => {
    const frames = [
      `event: message_chunk\ndata: ${JSON.stringify({ run_id: 'run-duplicate', durable: true, sequence: 1, content: 'once' })}\n\n`,
      `event: message_chunk\ndata: ${JSON.stringify({ run_id: 'run-duplicate', durable: true, sequence: 1, content: 'once' })}\n\n`,
      `event: run_completed\ndata: ${JSON.stringify({ run_id: 'run-duplicate', durable: true, sequence: 2 })}\n\n`,
      `event: run_completed\ndata: ${JSON.stringify({ run_id: 'run-duplicate', durable: true, sequence: 2 })}\n\n`,
    ].join('');
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(frames));
        controller.close();
      },
    });
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(body, { status: 200, headers: { 'Content-Type': 'text/event-stream' } }),
    );
    vi.stubGlobal('fetch', fetchMock);
    const chunks: string[] = [];
    const statuses: string[] = [];
    const views: Array<{ terminalStatus: string | null }> = [];

    await chatWithBackend({
      messages: [],
      provider: 'deepseek',
      onMessageChunk: chunk => chunks.push(chunk),
      onRunStatus: status => statuses.push(status.status),
      onRunView: view => views.push({ terminalStatus: view.terminalStatus }),
    });

    expect(chunks).toEqual(['once']);
    expect(statuses).toEqual(['succeeded']);
    expect(views.filter(view => view.terminalStatus !== null)).toEqual([{ terminalStatus: 'succeeded' }]);
  });

  it('reports recovery instead of treating a durable EOF without terminal as success', async () => {
    const liveBody = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(
          `event: thinking_start\ndata: ${JSON.stringify({ run_id: 'run-unknown-eof', durable: true, sequence: 1 })}\n\n`,
        ));
        controller.close();
      },
    });
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(liveBody, {
          status: 200,
          headers: { 'Content-Type': 'text/event-stream' },
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ events: [] }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      );
    vi.stubGlobal('fetch', fetchMock);
    const completions: unknown[] = [];
    const errors: string[] = [];

    await chatWithBackend({
      messages: [],
      provider: 'deepseek',
      onComplete: metadata => completions.push(metadata),
      onError: error => errors.push(error),
    });

    expect(completions).toEqual([]);
    expect(errors).toEqual(['运行流结束但未收到终态事件']);
  });

  it('allows an explicit legacy message_end completion for a non-durable stream', async () => {
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(
          'event: message_end\ndata: {"stream_sequence": 1}\n\n',
        ));
        controller.close();
      },
    });
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(body, { status: 200, headers: { 'Content-Type': 'text/event-stream' } }),
    );
    vi.stubGlobal('fetch', fetchMock);
    const completions: unknown[] = [];

    await chatWithBackend({
      messages: [],
      provider: 'deepseek',
      onComplete: metadata => completions.push(metadata),
    });

    expect(completions).toEqual([{ hasDurableRun: false, terminalStatus: null }]);
  });

  it('does not infer non-durable completion from a run id without metadata', async () => {
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(
          `event: message_end\ndata: ${JSON.stringify({ run_id: 'run-unknown', sequence: 1 })}\n\n`,
        ));
        controller.close();
      },
    });
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(body, { status: 200, headers: { 'Content-Type': 'text/event-stream' } }),
    );
    vi.stubGlobal('fetch', fetchMock);
    const completions: unknown[] = [];
    const errors: string[] = [];

    await chatWithBackend({
      messages: [],
      provider: 'deepseek',
      onComplete: metadata => completions.push(metadata),
      onError: error => errors.push(error),
    });

    expect(completions).toEqual([]);
    expect(errors).toEqual(['运行流结束但未收到终态事件']);
  });
});
