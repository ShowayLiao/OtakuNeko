import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import AIPage from '@/app/ai/page';
import {
  deleteUserMemory,
  listTasks,
  listTraces,
} from '@/services/ai';

let currentSection = 'traces';
const replace = vi.fn();

vi.mock('next/navigation', () => ({
  usePathname: () => '/ai',
  useRouter: () => ({ replace }),
  useSearchParams: () => new URLSearchParams(`section=${currentSection}`),
}));

vi.mock('antd', () => ({
  Tabs: ({
    activeKey,
    items,
  }: {
    activeKey: string;
    items: Array<{ key: string; children: React.ReactNode }>;
  }) => <div>{items.find((item) => item.key === activeKey)?.children}</div>,
}));

vi.mock('@lobehub/ui', () => ({
  Flexbox: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock('@/services/ai', () => ({
  deleteUserMemory: vi.fn(),
  listTasks: vi.fn(),
  listTraces: vi.fn(),
}));

describe('AI workspace', () => {
  beforeEach(() => {
    currentSection = 'traces';
    replace.mockReset();
    vi.mocked(listTraces).mockResolvedValue({
      traces: [],
      total: 0,
    });
    vi.mocked(listTasks).mockResolvedValue([]);
    vi.mocked(deleteUserMemory).mockResolvedValue({
      status: 'ok',
      user_id: 1,
      kind: null,
      deleted: 0,
    });
  });

  afterEach(cleanup);

  it('loads and renders trace data instead of placeholder content', async () => {
    vi.mocked(listTraces).mockResolvedValue({
      traces: [
        {
          trace_id: 'trace-123',
          agent_name: 'recommendation',
          goal: 'Recommend an anime',
          status: 'completed',
          started_at: '2026-07-30T01:00:00Z',
          steps: [],
        },
      ],
      total: 1,
    });

    render(<AIPage />);

    expect(await screen.findByText('Recommend an anime')).toBeTruthy();
    expect(screen.getByText('completed')).toBeTruthy();
    expect(listTraces).toHaveBeenCalledWith({ limit: 20 });
  });

  it('loads scheduled tasks for the tasks section', async () => {
    currentSection = 'tasks';
    vi.mocked(listTasks).mockResolvedValue([
      {
        id: 2,
        user_id: 1,
        task_type: 'weekly_recommendation',
        payload: '{}',
        schedule_expr: '0 9 * * 1',
        timezone: 'Asia/Shanghai',
        enabled: true,
        catch_up: 'latest',
        policy: '{}',
        created_at: '2026-07-30T01:00:00Z',
        updated_at: '2026-07-30T01:00:00Z',
      },
    ]);

    render(<AIPage />);

    expect(await screen.findByText('weekly_recommendation')).toBeTruthy();
    expect(screen.getByText('0 9 * * 1')).toBeTruthy();
  });

  it('requires confirmation before deleting all memory and reports the count', async () => {
    currentSection = 'settings';
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(deleteUserMemory).mockResolvedValue({
      status: 'ok',
      user_id: 1,
      kind: null,
      deleted: 4,
    });

    render(<AIPage />);
    fireEvent.click(screen.getByRole('button', { name: 'Delete all memory' }));

    await waitFor(() => expect(deleteUserMemory).toHaveBeenCalledWith());
    expect(await screen.findByText('Deleted 4 memory records.')).toBeTruthy();
  });
});
