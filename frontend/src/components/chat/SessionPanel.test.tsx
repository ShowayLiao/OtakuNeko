import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import SessionPanel from './SessionPanel';

vi.mock('@lobehub/ui', () => ({
  ActionIcon: ({
    onClick,
    title,
  }: {
    onClick?: React.MouseEventHandler<HTMLButtonElement>;
    title?: string;
  }) => (
    <button aria-label={title} onClick={onClick} type="button">
      {title}
    </button>
  ),
  DraggablePanel: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

describe('SessionPanel', () => {
  it('creates a session without forwarding the click event as a session id', () => {
    const onCreateSession = vi.fn();

    render(
      <SessionPanel
        activeSessionId={null}
        isDarkMode={false}
        onCreateSession={onCreateSession}
        onDeleteSession={vi.fn()}
        onSearchChange={vi.fn()}
        onSwitchSession={vi.fn()}
        sessionSearch=""
        sessions={[]}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: '新建会话' }));

    expect(onCreateSession).toHaveBeenCalledOnce();
    expect(onCreateSession.mock.calls[0]).toEqual([]);
  });

  it('renders one accessible delete control per session', () => {
    render(
      <SessionPanel
        activeSessionId="session-1"
        isDarkMode={false}
        onCreateSession={vi.fn()}
        onDeleteSession={vi.fn()}
        onSearchChange={vi.fn()}
        onSwitchSession={vi.fn()}
        sessionSearch=""
        sessions={[
          {
            id: 'session-1',
            title: '测试会话',
            updatedAt: new Date('2026-07-30T00:00:00Z'),
          },
        ]}
      />,
    );

    expect(screen.getByRole('heading', { name: '会话' })).toBeTruthy();
    expect(screen.getByRole('button', { name: '删除会话' })).toBeTruthy();
    expect(screen.getAllByRole('button', { name: '删除会话' })).toHaveLength(1);
  });
});
