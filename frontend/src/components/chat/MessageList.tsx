"use client";

import { memo } from 'react';
import { Copy, RotateCcw, MessageSquare, Pencil } from 'lucide-react';
import { ChatItem } from '@lobehub/ui/chat';
import { ActionIcon } from '@lobehub/ui';
import { theme } from 'antd';
import { useAppTheme } from '@/components/providers/LobeProvider';
import ContextPill from './ContextPill';
import AgentMessageRenderer from './AgentMessageRenderer';
import type { Message } from '@/stores/useChatStore';

interface MessageListProps {
  messages: Message[];
  streamingMessageId: string | null;
  onRegen: (msg: Message) => void;
  onEdit: (msg: Message) => void;
}

interface ContextReference {
  id: string;
  title: string;
  cover?: string;
  sourceId?: string | number;
}

const MemoChatItem = memo(ChatItem, (previous, next) => (
  previous.message === next.message
  && previous.time === next.time
  && previous.placement === next.placement
  && previous.aboveMessage === next.aboveMessage
));

export default function MessageList({
  messages,
  streamingMessageId,
  onRegen,
  onEdit,
}: MessageListProps) {
  const { isDarkMode } = useAppTheme();
  const { token } = theme.useToken();

  if (messages.length === 0) {
    return (
      <div style={{ textAlign: 'center', padding: 48, color: isDarkMode ? '#9ca3af' : '#6b7280' }}>
        <MessageSquare size={32} style={{ margin: '0 auto 16px' }} />
        <p style={{ fontSize: 16, marginBottom: 8 }}>没有消息</p>
        <p style={{ fontSize: 14 }}>开始与 OtakuNeko 聊天吧</p>
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto space-y-4">
      {messages.map((msg: Message, idx: number) => {
        const contextItems = Array.isArray(msg.extra?.contextItems)
          ? (msg.extra.contextItems as ContextReference[])
          : [];
        const isStreaming = msg.role === 'assistant' && msg.id === streamingMessageId;
        const showUserActions = msg.role === 'user';
        const streamVersion = isStreaming
          ? [
              msg.run ? `${msg.run.phase}:${msg.run.terminalStatus || ''}:${msg.run.lastSequence}` : '',
              ...(msg.processes || []).map((process) => `${process.id}:${process.status}:${String(process.details || '').length}`),
            ].join('|')
          : '';
        const streamSignal = isStreaming
          ? <span aria-hidden="true" style={{ display: 'none' }}>{streamVersion}</span>
          : undefined;

        const handleCopy = () => {
          navigator.clipboard.writeText(msg.content);
        };

        const prevMsg = idx > 0 ? messages[idx - 1] : null;
        const showDateSep = !prevMsg || !isSameDay(
          new Date(prevMsg.createdAt),
          new Date(msg.createdAt)
        );

        return (
          <div key={msg.id}>
            {showDateSep && (
              <div style={{ textAlign: 'center', padding: '8px 0' }}>
                <span
                  style={{
                    fontSize: 11,
                    padding: '3px 10px',
                    borderRadius: 10,
                    background: isDarkMode ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.04)',
                    color: isDarkMode ? '#9ca3af' : '#6b7280',
                  }}
                >
                  {formatDateLabel(new Date(msg.createdAt))}
                </span>
              </div>
            )}

            <MemoChatItem
              placement={msg.role === 'user' ? 'right' : 'left'}
              message={msg.content || ' '}
              aboveMessage={streamSignal}
              renderMessage={(defaultMessageNode) => (
                <AgentMessageRenderer
                  plan={msg.plan || ''}
                  processes={msg.processes || []}
                  isStreaming={isStreaming}
                  hasContent={!!msg.content}
                  isDarkMode={isDarkMode}
                  run={msg.run}
                  messageStatus={msg.status}
                  actions={
                    <div style={{ display: 'flex', gap: 6, marginTop: 2 }}>
                      {!isStreaming && msg.role === 'assistant' && msg.content && (
                        <>
                          <ActionIcon
                            icon={RotateCcw}
                            title="重新生成"
                            size={14}
                            onClick={() => onRegen(msg)}
                            style={{ opacity: 0.5, cursor: 'pointer' }}
                          />
                          <ActionIcon
                            icon={Copy}
                            title="复制"
                            size={14}
                            onClick={handleCopy}
                            style={{ opacity: 0.5, cursor: 'pointer' }}
                          />
                        </>
                      )}
                      {showUserActions && (
                        <ActionIcon
                          icon={Pencil}
                          title="重新编辑"
                          size={14}
                          onClick={() => onEdit(msg)}
                          style={{ opacity: 0.5, cursor: 'pointer' }}
                        />
                      )}
                    </div>
                  }
                >
                  {msg.content && defaultMessageNode}
                </AgentMessageRenderer>
              )}
              time={msg.createdAt instanceof Date ? msg.createdAt.getTime() : new Date(msg.createdAt).getTime()}
              avatar={{
                title: msg.role === 'user' ? '用户' : 'OtakuNeko',
                // 文本头像不会进入 antd Image 路径，避免 React 19 兼容性警告。
                avatar: msg.role === 'user' ? 'U' : 'O',
              }}
              avatarProps={{
                size: 40,
                style: {
                  imageRendering: 'auto',
                  WebkitFontSmoothing: 'antialiased',
                  objectFit: 'cover',
                  backgroundColor: msg.role === 'user' ? token.colorWarning : undefined,
                }
              }}
              messageExtra={
                msg.role === 'user' && contextItems.length > 0 && (
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 8 }}>
                    {contextItems.map((ref) => (
                      <ContextPill
                        key={ref.id}
                        item={ref}
                        darkMode={isDarkMode}
                        onClick={() => {
                          if (ref.sourceId) {
                            window.open(`https://bgm.tv/subject/${ref.sourceId}`, '_blank');
                          }
                        }}
                      />
                    ))}
                  </div>
                )
              }
            />
          </div>
        );
      })}
    </div>
  );
}

function isSameDay(a: Date, b: Date): boolean {
  return a.getFullYear() === b.getFullYear()
    && a.getMonth() === b.getMonth()
    && a.getDate() === b.getDate();
}

function formatDateLabel(d: Date): string {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const target = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const diff = (today.getTime() - target.getTime()) / 86400000;

  if (diff === 0) return '今天';
  if (diff === 1) return '昨天';
  if (diff < 7) return `${diff}天前`;
  return `${d.getFullYear()}/${d.getMonth() + 1}/${d.getDate()}`;
}
