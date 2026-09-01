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

  it('forwards an upstream Bearer challenge to the browser', async () => {
    vi.stubEnv('API_PROXY_URL', 'http://backend.test');
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Invalid authentication credentials' }), {
        status: 401,
        headers: {
          'content-type': 'application/json',
          'www-authenticate': 'Bearer',
        },
      }),
    ));

    const request = new Request('http://frontend.test/api/v1/chat', {
      method: 'POST',
      headers: {
        authorization: 'Bearer expired-user-token',
        'content-type': 'application/json',
      },
      body: JSON.stringify({ messages: [] }),
    });

    const response = await POST(request);

    expect(response.status).toBe(401);
    expect(response.headers.get('www-authenticate')).toBe('Bearer');
  });
});
