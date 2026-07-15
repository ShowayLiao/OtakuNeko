"use client";

import { useState, useRef } from 'react';
import { useEffect } from 'react';
import { v4 as uuidv4 } from 'uuid';
import { theme } from 'antd';
import { useAppTheme } from '@/components/providers/LobeProvider';
import { ChatInput } from './ChatInput';
import ApiKeyModal from '../Modal/ApiKeyModal';
import { fetchChatHistory, deleteChatHistory } from '@/lib/fetcher';
import useChatStore, { Message } from '../../stores/useChatStore';
import { useRoleStore } from '@/store/useRoleStore';
import presetRoles from '@/store/presetRoles';
import { useChatStreaming } from '@/hooks/useChatStreaming';
import SessionPanel from './SessionPanel';
import MessageList from './MessageList';
import { ChatErrorBoundary } from './ChatErrorBoundary';

export default function ChatPage() {
  const [selectedModel, setSelectedModel] = useState('gpt-3.5-turbo');
  const [selectedProvider, setSelectedProvider] = useState('openai');
  const [selectedRole, setSelectedRole] = useState('preset-1');
  const [isApiKeyModalOpen, setIsApiKeyModalOpen] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState<'connected' | 'connecting' | 'disconnected'>('connected');
  const [sessionSearch, setSessionSearch] = useState('');
  const [editText, setEditText] = useState<string | null>(null);

  const { token } = theme.useToken();
  const { isDarkMode } = useAppTheme();
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const {
    sessions,
    chatMessages,
    sessionConfigs,
    activeSessionId,
    createSession,
    sendMessage,
    switchSession,
    deleteSession,
    updateSessionTitle,
    setSessionMessages,
    setSessionConfig,
  } = useChatStore();

  useEffect(() => {
    if (!activeSessionId && sessions.length === 0) {
      createSession();
    }
  }, [activeSessionId, sessions.length, createSession]);

  useEffect(() => {
    if (activeSessionId) {
      const cfg = sessionConfigs[activeSessionId];
      if (cfg) {
        setSelectedModel(cfg.model);
        setSelectedProvider(cfg.provider);
        setSelectedRole(cfg.role);
      }
    }
  }, [activeSessionId]);

  useEffect(() => {
    if (!activeSessionId) return;
    const existingMsgs = chatMessages[activeSessionId];
    if (!existingMsgs || existingMsgs.length === 0) {
      const abortController = new AbortController();
      fetchChatHistory(activeSessionId, abortController.signal).then((serverMsgs) => {
        if (serverMsgs && serverMsgs.length > 0) {
          const formatted = serverMsgs.map((m: any) => ({
            id: `${activeSessionId}-${Date.now()}-${Math.random().toString(36).slice(2)}`,
            role: (m.role === 'human' ? 'user' : 'assistant') as Message['role'],
            content: m.content || '',
            createdAt: new Date(),
          }));
          setSessionMessages(activeSessionId, formatted);
        }
      }).catch(() => {});
      return () => abortController.abort();
    }
  }, [activeSessionId]);

  const currentMessages: Message[] = activeSessionId ? (chatMessages[activeSessionId] || []) : [];

  const handleModelChange = (modelId: string, provider: string) => {
    setSelectedModel(modelId);
    setSelectedProvider(provider);
    if (activeSessionId) {
      setSessionConfig(activeSessionId, { model: modelId, provider });
    }
  };

  const customRoles = useRoleStore((s) => s.customRoles);

  const handleRoleChange = (roleId: string) => {
    setSelectedRole(roleId);
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

  const { loading, startStreaming, stopGeneration } = useChatStreaming({
    selectedProvider,
    selectedModel,
    onConnectionStatusChange: setConnectionStatus,
  });

  const messageContainerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = messageContainerRef.current;
    if (!container) return;
    const isNearBottom = container.scrollTop + container.clientHeight >= container.scrollHeight - 150;
    if (isNearBottom) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [currentMessages, loading]);

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
    deleteChatHistory(sessionId).catch(() => {});
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
            className="flex-1 overflow-y-auto p-4"
            style={{ paddingBottom: 200 }}
          >
            <MessageList
              messages={currentMessages}
              loading={loading}
              onRegen={handleRegen}
              onStop={stopGeneration}
              onEdit={handleEdit}
            />
            <div ref={messagesEndRef} />
          </div>

          <ChatInput
            onSend={editText ? handleEditResend : handleSend}
            loading={loading}
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
