import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  deleteTask,
  deleteUserMemory,
  previewSchedule,
} from '@/services/ai';

function response(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: vi.fn().mockResolvedValue(body),
  } as unknown as Response;
}

describe('AI service client', () => {
  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem('token', 'test-token');
    vi.restoreAllMocks();
  });

  it('previews schedules through the authenticated GET query contract', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(response({ next_run: '2026-07-31T01:00:00Z' }));

    await expect(
      previewSchedule('0 9 * * *', 'Asia/Shanghai'),
    ).resolves.toEqual({ next_run: '2026-07-31T01:00:00Z' });

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/proactive/preview?schedule_expr=0+9+*+*+*&timezone=Asia%2FShanghai',
      expect.objectContaining({
        method: 'GET',
        headers: expect.objectContaining({
          Authorization: 'Bearer test-token',
        }),
      }),
    );
  });

  it('deletes a task with authentication and accepts a 204 body', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(response(undefined, 204));

    await expect(deleteTask(42)).resolves.toBeUndefined();

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/proactive/42',
      expect.objectContaining({
        method: 'DELETE',
        headers: expect.objectContaining({
          Authorization: 'Bearer test-token',
        }),
      }),
    );
  });

  it('deletes scoped memory through the authenticated client', async () => {
    const result = {
      status: 'ok',
      user_id: 7,
      kind: 'profile',
      deleted: 3,
    };
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(response(result));

    await expect(deleteUserMemory('profile')).resolves.toEqual(result);

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/memory?kind=profile',
      expect.objectContaining({
        method: 'DELETE',
        headers: expect.objectContaining({
          Authorization: 'Bearer test-token',
        }),
      }),
    );
  });
});
