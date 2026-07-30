import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import SessionPanel from './SessionPanel';

vi.mock('@lobehub/ui', () => ({
  ActionIcon: ({ title }: { title?: string }) => <span>{title}</span>,
  DraggablePanel: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

describe('SessionPanel', () => {
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
