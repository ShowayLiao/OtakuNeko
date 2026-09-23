"use client";
/* eslint-disable @typescript-eslint/no-explicit-any -- persisted sessions contain legacy fields. */

import { useMemo, useState, useRef } from 'react';
import { useEffect } from 'react';
import { v4 as uuidv4 } from 'uuid';
import { useAppTheme } from '@/components/providers/LobeProvider';
import { ChatInput } from './ChatInput';
import ApiKeyModal from '../Modal/ApiKeyModal';
import {
  AUTH_STATE_CHANGED_EVENT,
  deleteChatHistory,
  fetchChatHistory,
  fetchCurrentUser,
  listThreads,
} from '@/lib/fetcher';
import useChatStore, { Message } from '../../stores/useChatStore';
import { useRoleStore } from '@/store/useRoleStore';
import presetRoles from '@/store/presetRoles';
import { useChatStreaming } from '@/hooks/useChatStreaming';
import SessionPanel from './SessionPanel';
import MessageList from './MessageList';
import { ChatErrorBoundary } from './ChatErrorBoundary';
import { useApiStore } from '@/store/useApiStore';
import { resolveChatSelection } from '@/lib/chatDefaults';

const EMPTY_MESSAGES: Message[] = [];
type AuthState = 'loading' | 'authenticated' | 'anonymous';

export default function ChatPage() {
  const [isApiKeyModalOpen, setIsApiKeyModalOpen] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState<'connected' | 'connecting' | 'disconnected'>('connected');
  const [sessionSearch, setSessionSearch] = useState('');
  const [editText, setEditText] = useState<string | null>(null);
  const [authState, setAuthState] = useState<AuthState>('loading');
  const [authRefresh, setAuthRefresh] = useState(0);

  const { isDarkMode } = useAppTheme();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const resumedRunIdsRef = useRef(new Set<string>());

  const sessions = useChatStore((state) => state.sessions);
  const activeSessionId = useChatStore((state) => state.activeSessionId);
  const sessionConfigs = useChatStore((state) => state.sessionConfigs);
  const activeSessionConfig = activeSessionId ? sessionConfigs[activeSessionId] : undefined;
  const apiConfig = useApiStore((state) => state.config);
  const { model: selectedModel, provider: selectedProvider } = resolveChatSelection(
    activeSessionConfig,
    apiConfig,
  );
  const selectedRole = activeSessionConfig?.role ?? 'preset-1';
  const currentMessages = useChatStore((state) => (
    activeSessionId ? state.chatMessages[activeSessionId] || EMPTY_MESSAGES : EMPTY_MESSAGES
  ));
  const createSession = useChatStore((state) => state.createSession);
  const sendMessage = useChatStore((state) => state.sendMessage);
  const switchSession = useChatStore((state) => state.switchSession);
  const deleteSession = useChatStore((state) => state.deleteSession);
  const updateSessionTitle = useChatStore((state) => state.updateSessionTitle);
  const setSessionMessages = useChatStore((state) => state.setSessionMessages);
  const setSessionConfig = useChatStore((state) => state.setSessionConfig);
  const loadSessions = useChatStore((state) => state.loadSessions);
  const resetChat = useChatStore((state) => state.resetChat);

  useEffect(() => {
    const refreshAuth = () => setAuthRefresh((value) => value + 1);
    window.addEventListener(AUTH_STATE_CHANGED_EVENT, refreshAuth);
    return () => window.removeEventListener(AUTH_STATE_CHANGED_EVENT, refreshAuth);
  }, []);

  useEffect(() => {
    let cancelled = false;
    const resolveAuth = async () => {
      if (!localStorage.getItem('token')) return null;
      return fetchCurrentUser();
    };

    void resolveAuth()
      .then((user) => {
        if (!cancelled) setAuthState(user ? 'authenticated' : 'anonymous');
      })
      .catch(() => {
        if (!cancelled) setAuthState('anonymous');
      });

    return () => { cancelled = true; };
  }, [authRefresh]);

  useEffect(() => {
    if (authState === 'loading') return;
    let cancelled = false;
    resetChat();

    if (authState === 'anonymous') {
      createSession();
      return () => { cancelled = true; };
    }

    listThreads()
      .then((threadIds) => {
        if (cancelled) return;
        loadSessions(threadIds);
        if (threadIds.length === 0) createSession();
      })
      .catch(() => {
        if (cancelled) return;
        resetChat();
        createSession();
      });

    return () => { cancelled = true; };
  }, [authState, createSession, loadSessions, resetChat]);

  useEffect(() => {
    if (authState !== 'authenticated' || !activeSessionId) return;
    const abortController = new AbortController();
    fetchChatHistory(activeSessionId, abortController.signal)
      .then((serverMsgs) => {
        if (abortController.signal.aborted) return;
        const current = useChatStore.getState().chatMessages[activeSessionId] || [];
        if (current.length > 0 || serverMsgs.length === 0) return;
        const formatted = serverMsgs.map((m: any, index: number) => ({
          id: `${activeSessionId}-${index}`,
          role: (m.role === 'human' ? 'user' : m.role) as Message['role'],
          content: m.content || '',
          createdAt: new Date(),
        }));
        setSessionMessages(activeSessionId, formatted);
      })
      .catch(() => {});
    return () => abortController.abort();
  }, [activeSessionId, authState, setSessionMessages]);

  const handleModelChange = (modelId: string, provider: string) => {
    if (activeSessionId) {
      setSessionConfig(activeSessionId, { model: modelId, provider });
    }
  };

  const customRoles = useRoleStore((s) => s.customRoles);

  const handleRoleChange = (roleId: string) => {
    if (activeSessionId) {
      setSessionConfig(activeSessionId, { role: roleId });
    }
  };

  const getSelectedRole = () => {
    const allRoles = [...presetRoles, ...customRoles];
    return allRoles.find(role => role.id === selectedRole);
  };

  const handleOpenSettings = () => {
    setIsApiKeyModalOpen(true);
  };

  const {
    loading,
    cancelling,
    streamingMessageId,
    streamingPreview,
    startStreaming,
    resumeRun,
    stopGeneration,
  } = useChatStreaming({
    selectedProvider,
    selectedModel,
    onConnectionStatusChange: setConnectionStatus,
  });

  useEffect(() => {
    if (authRefresh > 0) stopGeneration();
  }, [authRefresh, stopGeneration]);

  const displayMessages = useMemo(() => {
    if (!streamingPreview) return currentMessages;
    return currentMessages.map((message) => (
      message.id === streamingPreview.messageId
        ? {
          ...message,
          content: streamingPreview.content,
          processes: streamingPreview.processes,
          plan: streamingPreview.plan,
          status: streamingPreview.status,
          run: streamingPreview.run,
        }
        : message
    ));
  }, [currentMessages, streamingPreview]);

  useEffect(() => {
    if (!activeSessionId || loading) return;
    const resumable = currentMessages.find((message) => (
      message.role === 'assistant'
      && message.run?.durable === true
      && Boolean(message.run.runId)
      && !message.run.terminalStatus
    ));
    const runId = resumable?.run?.runId;
    if (!resumable || !runId || resumedRunIdsRef.current.has(runId)) return;
    resumedRunIdsRef.current.add(runId);
    void resumeRun({
      sessionId: activeSessionId,
      messageId: resumable.id,
      run: resumable.run!,
      content: resumable.content,
      processes: resumable.processes,
      plan: resumable.plan,
    });
  }, [activeSessionId, currentMessages, loading, resumeRun]);

  const messageContainerRef = useRef<HTMLDivElement>(null);

  const shouldStickToBottomRef = useRef(true);

  const scrollFrameRef = useRef<number | null>(null);

  useEffect(() => {
    if (!shouldStickToBottomRef.current || scrollFrameRef.current !== null) return;
    scrollFrameRef.current = requestAnimationFrame(() => {
      scrollFrameRef.current = null;
      const container = messageContainerRef.current;
      if (container && shouldStickToBottomRef.current) {
        container.scrollTop = container.scrollHeight;
      }
    });
    return () => {
      if (scrollFrameRef.current !== null) {
        cancelAnimationFrame(scrollFrameRef.current);
        scrollFrameRef.current = null;
      }
    };
  }, [displayMessages, loading]);

  const handleMessageScroll = () => {
    const container = messageContainerRef.current;
    if (!container) return;
    shouldStickToBottomRef.current =
      container.scrollTop + container.clientHeight >= container.scrollHeight - 150;
  };

  const getMessagesForBackend = () => {
    return currentMessages
      .filter((m: Message) => m.role === 'user' || m.role === 'assistant')
      .map((m: Message) => ({ role: m.role, content: m.content }));
  };

  const sessionTitle = activeSessionId
    ? sessions.find(s => s.id === activeSessionId)?.title
    : undefined;

  useEffect(() => {
    if (!activeSessionId || sessionTitle !== '新会话') return;
    const assistantMsgs = currentMessages.filter(m => m.role === 'assistant' && m.content);
    if (assistantMsgs.length === 0) return;
    const raw = assistantMsgs[0].content.replace(/[#\*\n\r]/g, '').trim().slice(0, 16);
    if (raw) {
      updateSessionTitle(activeSessionId, raw + (assistantMsgs[0].content.length > 16 ? '…' : ''));
    }
  }, [currentMessages, activeSessionId, sessionTitle]);

  const handleRegen = async (msg: Message) => {
    const idx = currentMessages.indexOf(msg);
    if (idx < 1 || !activeSessionId) return;
    const prevMessages = currentMessages.slice(0, idx);

    const aiMessageId = uuidv4();
    const aiMessage: Message = {
      id: aiMessageId,
      role: 'assistant',
      content: '',
      createdAt: new Date(),
    };
    sendMessage(activeSessionId, aiMessage);

    await startStreaming({
      messages: prevMessages
        .filter((m: Message) => m.role === 'user' || m.role === 'assistant')
        .map((m: Message) => ({ role: m.role, content: m.content })),
      temperature: 0.7,
      activeSessionId,
      aiMessageId,
    });
  };

  const handleSend = async (text: string, contextItems: any[]) => {
    if (!text.trim() && contextItems.length === 0) return;
    if (!activeSessionId) return;

    const userMessage: Message = {
      id: uuidv4(),
      role: 'user',
      content: text,
      createdAt: new Date(),
      extra: { contextItems },
    };
    sendMessage(activeSessionId, userMessage);

    let userContent = text;
    if (contextItems.length > 0) {
      const contextXml = contextItems.map((item: any) =>
        `<Entity id="${item.id}" source="${item.source}" sourceId="${item.sourceId}">${item.title}</Entity>`
      ).join('\n');
      userContent = `Context:\n${contextXml}\n\nUser Question:\n${text}`;
    }

    const formattedMessages = [
      ...getMessagesForBackend(),
      { role: 'user', content: userContent },
    ];

    const selectedRoleObj = getSelectedRole();
    const prompt_config = selectedRoleObj ? selectedRoleObj.promptConfig : undefined;

    const aiMessageId = uuidv4();
    const aiMessage: Message = {
      id: aiMessageId,
      role: 'assistant',
      content: '',
      createdAt: new Date(),
    };
    sendMessage(activeSessionId, aiMessage);

    await startStreaming({
      messages: formattedMessages,
      temperature: selectedRoleObj?.temperature || 0.7,
      promptConfig: prompt_config,
      activeSessionId,
      aiMessageId,
    });
  };

  const handleEdit = (msg: Message) => {
    setEditText(msg.content);
  };

  const handleEditResend = async (text: string, contextItems: any[]) => {
    setEditText(null);
    await handleSend(text, contextItems);
  };

  const handleDeleteSession = (sessionId: string) => {
    if (authState === 'authenticated') deleteChatHistory(sessionId).catch(() => {});
    deleteSession(sessionId);
  };

  return (
    <ChatErrorBoundary>
      <div
        className="flex-1 flex min-h-0 w-full relative overflow-hidden"
        style={{ background: 'transparent' }}
      >
        <SessionPanel
          sessions={sessions}
          activeSessionId={activeSessionId}
          sessionSearch={sessionSearch}
          isDarkMode={isDarkMode}
          onSearchChange={setSessionSearch}
          onCreateSession={createSession}
          onSwitchSession={switchSession}
          onDeleteSession={handleDeleteSession}
        />

        <div className="flex-1 flex flex-col min-h-0 relative overflow-hidden">
          <div
            ref={messageContainerRef}
            onScroll={handleMessageScroll}
            className="flex-1 overflow-y-auto p-4"
            style={{ paddingBottom: 200 }}
          >
            <MessageList
              messages={displayMessages}
              streamingMessageId={streamingMessageId}
              onRegen={handleRegen}
              onEdit={handleEdit}
            />
            <div ref={messagesEndRef} />
          </div>

          <ChatInput
            key={editText ?? 'new-message'}
            onSend={editText ? handleEditResend : handleSend}
            onStop={stopGeneration}
            loading={loading}
            cancelling={cancelling}
            selectedModel={selectedModel}
            selectedProvider={selectedProvider}
            onModelChange={handleModelChange}
            onOpenSettings={handleOpenSettings}
            selectedRole={selectedRole}
            onRoleChange={handleRoleChange}
            connectionStatus={connectionStatus}
            editText={editText}
            onEditCancel={() => setEditText(null)}
          />
        </div>

        <ApiKeyModal open={isApiKeyModalOpen} onClose={() => setIsApiKeyModalOpen(false)} />
      </div>
    </ChatErrorBoundary>
  );
}
