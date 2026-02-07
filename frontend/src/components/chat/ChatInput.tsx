"use client";

import { useState } from 'react';
import { Languages, Eraser, X } from 'lucide-react';
import { theme } from 'antd';
import { ChatInputArea, ChatInputActionBar, TokenTag, ChatSendButton } from '@lobehub/ui/chat';
import { ActionIcon } from '@lobehub/ui';
import { Avatar } from '@lobehub/ui';
import { useAppTheme } from '@/components/providers/LobeProvider';
import { ModelSelector } from './ModelSelector';
import SearchTrigger, { SearchResultItem } from './SearchBar';

interface ChatInputProps {
  onSend: (text: string, contextItems: SearchResultItem[]) => void;
  loading: boolean;
  selectedModel: string;
  selectedProvider: string;
  onModelChange: (modelId: string, provider: string) => void;
  onOpenSettings: () => void;
}

export const ChatInput = ({
  onSend,
  loading,
  selectedModel,
  selectedProvider,
  onModelChange,
  onOpenSettings,
}: ChatInputProps) => {
  const [isExpand, setIsExpand] = useState(false);
  const [text, setText] = useState('');
  const [contextItems, setContextItems] = useState<SearchResultItem[]>([]);
  const heights = {
    inputHeight: 160, 
    minHeight: 128,
    maxHeight: 600, 
  };

  const { token } = theme.useToken();
  const { isDarkMode } = useAppTheme();

  // 处理搜索结果选择
  const handleSearchSelect = (item: SearchResultItem) => {
    // 去重：检查是否已经存在相同的项
    const isDuplicate = contextItems.some(
      existingItem => existingItem.id === item.id
    );
    
    if (!isDuplicate) {
      setContextItems(prev => [...prev, item]);
    }
  };

  // 处理胶囊删除
  const handleRemoveContextItem = (index: number) => {
    setContextItems(prev => prev.filter((_, i) => i !== index));
  };

  // 处理发送
  const handleSend = () => {
    if (!text.trim() && contextItems.length === 0) return;
    
    onSend(text, contextItems);
    // 清空文本和胶囊
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
      {/* 胶囊容器 */}
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
            <div
              key={item.id}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                padding: '6px 10px',
                borderRadius: 20,
                backgroundColor: isDarkMode ? 'rgba(75, 85, 99, 0.5)' : 'rgba(229, 231, 235, 0.8)',
                border: `1px solid ${isDarkMode ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.1)'}`,
                backdropFilter: 'saturate(180%) blur(12px)',
                transition: 'all 0.2s ease',
              }}
            >
              {/* 封面小图 */}
              <Avatar
                size={24}
                style={{
                  borderRadius: 4,
                  objectFit: 'cover',
                }}
                avatar={item.cover || '/Icon.png'}
              />
              
              {/* 标题文本 */}
              <span style={{ fontSize: 12, fontWeight: 500 }}>
                {item.title}
              </span>
              
              {/* 删除按钮 */}
              <ActionIcon
                icon={X}
                size={{ blockSize: 16 }}
                onClick={() => handleRemoveContextItem(index)}
                style={{
                  cursor: 'pointer',
                  opacity: 0.7,
                  transition: 'opacity 0.2s ease'
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.opacity = '1';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.opacity = '0.7';
                }}
              />
            </div>
          ))}
        </div>
      )}

      {/* 输入区域 */}
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
                  <SearchTrigger onSelect={handleSearchSelect} />
                  <ActionIcon icon={Languages} title="翻译" />
                  <ActionIcon icon={Eraser} title="清除" />
                  <TokenTag maxValue={5000} value={1000} />
                </div>
              }
            />
          }
        bottomAddons={<ChatSendButton loading={loading} onSend={handleSend} />}
        
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
          
          borderRadius: 16,
          overflow: 'hidden',
        }}
        className="w-full"
      />

      {/* 添加淡入动画样式 */}
      <style jsx>{`
        @keyframes fadeIn {
          from {
            opacity: 0;
            transform: translateY(-10px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }
      `}</style>
    </div>
  );
};

export default ChatInput;