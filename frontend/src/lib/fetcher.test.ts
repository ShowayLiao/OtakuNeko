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
});
