import { afterEach, describe, expect, it } from 'vitest';

import useChatStore from './useChatStore';

const resetState = () => {
  useChatStore.setState({
    sessions: [],
    chatMessages: {},
    sessionConfigs: {},
    activeSessionId: null,
  });
  localStorage.clear();
};

describe('useChatStore privacy boundaries', () => {
  afterEach(resetState);

  it('does not persist chat content in browser storage', () => {
    const sessionId = useChatStore.getState().createSession();
    useChatStore.getState().sendMessage(sessionId, 'private message');

    expect(localStorage.getItem('chat-storage')).toBeNull();
  });

  it('clears all in-memory chat state on reset', () => {
    const sessionId = useChatStore.getState().createSession();
    useChatStore.getState().sendMessage(sessionId, 'private message');
    localStorage.setItem('chat-storage', 'legacy-content');

    useChatStore.getState().resetChat();

    expect(useChatStore.getState().sessions).toEqual([]);
    expect(useChatStore.getState().chatMessages).toEqual({});
    expect(useChatStore.getState().activeSessionId).toBeNull();
    expect(localStorage.getItem('chat-storage')).toBeNull();
  });

  it('loads unique server thread ids without carrying over local messages', () => {
    const oldSessionId = useChatStore.getState().createSession('old-session');
    useChatStore.getState().sendMessage(oldSessionId, 'old local message');

    useChatStore.getState().loadSessions(['server-thread-1', 'server-thread-1', 'server-thread-2']);

    expect(useChatStore.getState().sessions.map((session) => session.id)).toEqual([
      'server-thread-1',
      'server-thread-2',
    ]);
    expect(useChatStore.getState().chatMessages).toEqual({
      'server-thread-1': [],
      'server-thread-2': [],
    });
    expect(useChatStore.getState().activeSessionId).toBe('server-thread-1');
  });
});
