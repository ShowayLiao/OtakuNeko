"use client";

import { Plus, Trash2, MessageSquare, Search } from 'lucide-react';
import { ActionIcon, DraggablePanel } from '@lobehub/ui';
import type { Session } from '@/stores/useChatStore';

interface SessionPanelProps {
  sessions: Session[];
  activeSessionId: string | null;
  sessionSearch: string;
  isDarkMode: boolean;
  onSearchChange: (value: string) => void;
  onCreateSession: () => void;
  onSwitchSession: (id: string) => void;
  onDeleteSession: (id: string) => void;
}

export default function SessionPanel({
  sessions,
  activeSessionId,
  sessionSearch,
  isDarkMode,
  onSearchChange,
  onCreateSession,
  onSwitchSession,
  onDeleteSession,
}: SessionPanelProps) {
  const filteredSessions = sessionSearch
    ? sessions.filter(s => s.title.toLowerCase().includes(sessionSearch.toLowerCase()))
    : sessions;

  return (
    <DraggablePanel
      defaultExpand={true}
      expandable={true}
      minWidth={200}
      mode="fixed"
      pin={true}
      placement="left"
      showBorder={true}
      style={{
        background: isDarkMode ? '#1e1e1e' : '#ffffff',
      }}
    >
      <div style={{ height: '100%', display: 'flex', flexDirection: 'column', padding: 16 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <h3 style={{ margin: 0, fontSize: 16, fontWeight: 'bold' }}>会话</h3>
          <ActionIcon
            icon={Plus}
            title="新建会话"
            onClick={onCreateSession}
            style={{ cursor: 'pointer' }}
          />
        </div>

        <div style={{ marginBottom: 8, position: 'relative' }}>
          <input
            type="text"
            value={sessionSearch}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="搜索会话..."
            style={{
              width: '100%',
              padding: '6px 10px 6px 30px',
              borderRadius: 8,
              border: `1px solid ${isDarkMode ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.1)'}`,
              background: isDarkMode ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.03)',
              color: isDarkMode ? '#d1d5db' : '#374151',
              fontSize: 13,
              outline: 'none',
            }}
          />
          <Search size={14} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', opacity: 0.4 }} />
        </div>

        <div style={{ flex: 1, overflowY: 'auto', gap: 8, display: 'flex', flexDirection: 'column' }}>
          {filteredSessions.map((session) => (
            <div
              key={session.id}
              style={{
                padding: 12,
                borderRadius: 8,
                cursor: 'pointer',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'flex-start',
                backgroundColor: activeSessionId === session.id
                  ? (isDarkMode ? 'rgba(75, 85, 99, 0.5)' : 'rgba(229, 231, 235, 0.8)')
                  : 'transparent',
                border: `1px solid ${isDarkMode ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.1)'}`,
                transition: 'all 0.2s ease',
              }}
              onClick={() => onSwitchSession(session.id)}
            >
              <div style={{ flex: 1, marginRight: 8 }}>
                <div style={{ fontWeight: '500', fontSize: 14, marginBottom: 4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {session.title}
                </div>
                <div style={{ fontSize: 12, color: isDarkMode ? '#9ca3af' : '#6b7280' }}>
                  {(() => {
                    try {
                      const d = session.updatedAt instanceof Date ? session.updatedAt : new Date(session.updatedAt as unknown as string);
                      if (isNaN(d.getTime())) return '';
                      return d.toLocaleString();
                    } catch { return ''; }
                  })()}
                </div>
              </div>
              <div style={{ flexShrink: 0, marginLeft: 4 }}>
                <ActionIcon
                  icon={Trash2}
                  title="删除会话"
                  size={16}
                  onClick={(e) => {
                    e.stopPropagation();
                    onDeleteSession(session.id);
                  }}
                  style={{ color: isDarkMode ? '#ef4444' : '#dc2626', cursor: 'pointer' }}
                />
              </div>
            </div>
          ))}

          {sessions.length === 0 && (
            <div style={{ textAlign: 'center', padding: 24, color: isDarkMode ? '#9ca3af' : '#6b7280' }}>
              <MessageSquare size={24} style={{ margin: '0 auto 8px' }} />
              <p>没有会话</p>
              <p style={{ fontSize: 12 }}>点击上方按钮创建新会话</p>
            </div>
          )}
        </div>
      </div>
    </DraggablePanel>
  );
}
