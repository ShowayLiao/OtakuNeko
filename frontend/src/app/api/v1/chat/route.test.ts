import { afterEach, describe, expect, it, vi } from 'vitest';

import { POST } from './route';

describe('chat proxy authentication', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('forwards the browser authorization header upstream', async () => {
    vi.stubEnv('API_PROXY_URL', 'http://backend.test');
    const fetchMock = vi.fn().mockResolvedValue(
      new Response('data: {}\n\n', {
        status: 200,
        headers: { 'content-type': 'text/event-stream' },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const request = new Request('http://frontend.test/api/v1/chat', {
      method: 'POST',
      headers: {
        authorization: 'Bearer user-access-token',
        'content-type': 'application/json',
        'x-api-key': 'provider-key',
      },
      body: JSON.stringify({ messages: [] }),
    });

    await POST(request);

    const upstreamInit = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(new Headers(upstreamInit.headers).get('authorization')).toBe(
      'Bearer user-access-token',
    );
  });
});
