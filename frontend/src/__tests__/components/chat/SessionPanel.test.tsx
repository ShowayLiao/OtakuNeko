import { useState, type ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';

import SessionPanel from '@/components/chat/SessionPanel';

// jsdom cannot resize the real panel; reproduce its controlled/uncontrolled
// expansion contract while exercising SessionPanel's actual event handlers.
vi.mock('@lobehub/ui', () => ({
  ActionIcon: ({ onClick }: { onClick: () => void }) => <button onClick={onClick}>New session</button>,
  DraggablePanel: ({
    children,
    defaultExpand,
    expand,
    onExpandChange,
  }: {
    children: ReactNode;
    defaultExpand: boolean;
    expand?: boolean;
    onExpandChange?: (value: boolean) => void;
  }) => {
    const [internalExpand, setInternalExpand] = useState(defaultExpand);
    const expanded = expand ?? internalExpand;
    return (
      <section>
        <button onClick={() => {
          setInternalExpand(!expanded);
          onExpandChange?.(!expanded);
        }}>Toggle panel</button>
        <div hidden={!expanded}>{children}</div>
      </section>
    );
  },
}));

afterEach(cleanup);

const panelProps = {
  sessions: [],
  activeSessionId: null,
  sessionSearch: '',
  isDarkMode: false,
  onSearchChange: vi.fn(),
  onCreateSession: vi.fn(),
  onSwitchSession: vi.fn(),
  onDeleteSession: vi.fn(),
};

function MobilePanel() {
  const [mobileOpen, setMobileOpen] = useState(true);
  return (
    <>
      <button onClick={() => setMobileOpen(true)}>Open drawer</button>
      <button onClick={() => setMobileOpen(false)}>Close drawer</button>
      <div hidden={!mobileOpen}>
        <SessionPanel
          {...panelProps}
          mobileOpen={mobileOpen}
          onCloseMobile={() => setMobileOpen(false)}
        />
      </div>
    </>
  );
}

describe('SessionPanel expansion', () => {
  it('shows the session list when reopening a drawer after native panel collapse', () => {
    render(<MobilePanel />);
    fireEvent.click(screen.getByRole('button', { name: 'Toggle panel' }));
    fireEvent.click(screen.getByRole('button', { name: 'Close drawer' }));
    fireEvent.click(screen.getByRole('button', { name: 'Open drawer' }));

    expect(screen.getByRole('heading', { name: '会话' })).toBeDefined();
  });

  it('closes the mobile drawer when collapsing the panel', () => {
    render(<MobilePanel />);
    fireEvent.click(screen.getByRole('button', { name: 'Toggle panel' }));

    expect(screen.queryByRole('button', { name: 'Toggle panel' })).toBeNull();
  });

  it('preserves desktop collapse and expand behavior', () => {
    render(<SessionPanel {...panelProps} />);
    fireEvent.click(screen.getByRole('button', { name: 'Toggle panel' }));
    expect(screen.queryByRole('heading', { name: '会话' })).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Toggle panel' }));
    expect(screen.getByRole('heading', { name: '会话' })).toBeDefined();
  });
});
