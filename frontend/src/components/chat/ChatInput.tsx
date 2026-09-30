"use client";

import { useState } from 'react';
import { Eraser, X } from 'lucide-react';
import { theme } from 'antd';
import { ChatInputArea, ChatInputActionBar, ChatSendButton } from '@lobehub/ui/chat';
import { ActionIcon } from '@lobehub/ui';
import { useAppTheme } from '@/components/providers/LobeProvider';
import { ModelSelector } from './ModelSelector';
import { RoleSelector } from './RoleSelector';
import SearchTrigger, { SearchResultItem } from './SearchBar';
import ConnectionStatus from './ConnectionStatus';
import ContextPill from './ContextPill';

interface ChatInputProps {
  onSend: (text: string, contextItems: SearchResultItem[]) => void;
  onStop: () => void;
  loading: boolean;
  cancelling?: boolean;
  selectedModel: string;
  selectedProvider: string;
  onModelChange: (modelId: string, provider: string) => void;
  onOpenSettings: () => void;
  selectedRole: string;
  onRoleChange: (roleId: string) => void;
  connectionStatus?: 'connected' | 'connecting' | 'disconnected';
  editText?: string | null;
  onEditCancel?: () => void;
}

export const ChatInput = ({
  onSend,
  onStop,
  loading,
  cancelling = false,
  selectedModel,
  selectedProvider,
  onModelChange,
  onOpenSettings,
  selectedRole,
  onRoleChange,
  connectionStatus,
  editText,
  onEditCancel,
}: ChatInputProps) => {
  const [isExpand, setIsExpand] = useState(false);
  const [text, setText] = useState(() => editText ?? '');
  const [contextItems, setContextItems] = useState<SearchResultItem[]>([]);
  const heights = {
    inputHeight: 160,
    minHeight: 128,
    maxHeight: 600,
  };

  const { token } = theme.useToken();
  const { isDarkMode } = useAppTheme();

  const handleSearchSelect = (item: SearchResultItem) => {
    const isDuplicate = contextItems.some(
      existingItem => existingItem.id === item.id
    );
    if (!isDuplicate) {
      setContextItems(prev => [...prev, item]);
    }
  };

  const handleRemoveContextItem = (index: number) => {
    setContextItems(prev => prev.filter((_, i) => i !== index));
  };

  const handleSend = () => {
    if (!text.trim() && contextItems.length === 0) return;
    onSend(text, contextItems);
    setText('');
    setContextItems([]);
  };

  const handleClear = () => {
    setText('');
    setContextItems([]);
  };

  return (
    <div
      style={{
        position: 'absolute',
        bottom: 0,
        left: 0,
        width: '100%',
        padding: '0 16px 24px 16px',
        zIndex: 10,
      }}
    >
      {editText && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            padding: '6px 0',
            fontSize: 12,
            color: isDarkMode ? '#fbbf24' : '#d97706',
          }}
        >
          <span>正在编辑消息</span>
          <ActionIcon
            icon={X}
            size={{ blockSize: 14 }}
            title="取消编辑"
            onClick={onEditCancel}
          />
        </div>
      )}

      {cancelling && (
        <div role="status" style={{ padding: '6px 0', fontSize: 12, color: isDarkMode ? '#fbbf24' : '#b45309' }}>
          Cancelling run… waiting for the cancellation event.
        </div>
      )}

      {contextItems.length > 0 && (
        <div
          style={{
            display: 'flex',
            gap: 8,
            flexWrap: 'wrap',
            padding: '12px 0',
            animation: 'fadeIn 0.3s ease-in-out',
          }}
        >
          {contextItems.map((item, index) => (
            <ContextPill
              key={item.id}
              item={item}
              darkMode={isDarkMode}
              onRemove={() => handleRemoveContextItem(index)}
            />
          ))}
        </div>
      )}

      <ChatInputArea
        topAddons={
          <ChatInputActionBar
            leftAddons={
              <div style={{ marginLeft: '20px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <ModelSelector
                  value={selectedModel}
                  onChange={onModelChange}
                  onOpenSettings={onOpenSettings}
                />
                <RoleSelector
                  value={selectedRole}
                  onChange={onRoleChange}
                />
                <SearchTrigger onSelect={handleSearchSelect} />
                <ActionIcon icon={Eraser} title="清除" onClick={handleClear} />
                {connectionStatus && <ConnectionStatus status={connectionStatus} />}
              </div>
            }
          />
        }
        bottomAddons={<ChatSendButton loading={loading} onSend={handleSend} onStop={onStop} />}
        expand={isExpand}
        setExpand={setIsExpand}
        heights={heights}
        value={text}
        onInput={setText}
        onSend={handleSend}
        placeholder="输入消息..."
        style={{
          background: isDarkMode
            ? 'rgba(30, 30, 30, 0.6)'
            : 'rgba(255, 255, 255, 0.6)',
          backdropFilter: 'saturate(180%) blur(12px)',
          border: `1px solid ${isDarkMode ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.06)'}`,
          boxShadow: isDarkMode
            ? '0 8px 32px 0 rgba(0, 0, 0, 0.3), inset 0 1px 0 0 rgba(255, 255, 255, 0.05)'
            : '0 8px 32px 0 rgba(0, 0, 0, 0.08), inset 0 1px 0 0 rgba(255, 255, 255, 0.6)',
        }}
      />
    </div>
  );
};
