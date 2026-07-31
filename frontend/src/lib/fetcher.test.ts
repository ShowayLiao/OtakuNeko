import { afterEach, describe, expect, it, vi } from 'vitest';

import { chatWithBackend } from './fetcher';

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

  it('replays durable events after a disconnect without resubmitting the chat POST', async () => {
    const liveFrames = [
      `id: 1\nevent: thinking_start\ndata: ${JSON.stringify({ run_id: 'run-1', stream_sequence: 1 })}\n\n`,
      `id: 2\nevent: message_chunk\ndata: ${JSON.stringify({ run_id: 'run-1', stream_sequence: 2, content: 'partial' })}\n\n`,
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
});
