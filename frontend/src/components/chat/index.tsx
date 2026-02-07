"use client";

import { useState, useRef, useEffect } from 'react';
import { v4 as uuidv4 } from 'uuid';
// 1. 引入图标并重命名，防止命名冲突
import { User as UserIcon, Bot as BotIcon, Plus, Trash2, MessageSquare } from 'lucide-react';
import { theme } from 'antd';
import { ChatItem } from '@lobehub/ui/chat';
import { ActionIcon, DraggablePanel } from '@lobehub/ui';
import { useAppTheme } from '@/components/providers/LobeProvider';
import { ModelSelector } from './ModelSelector';
import SearchTrigger, { SearchResultItem } from './SearchBar';
import ChatInput from './ChatInput';
import ApiKeyModal from '../Modal/ApiKeyModal';
import { chatWithBackend } from '@/lib/fetcher';
import useChatStore, { Message } from '../../stores/useChatStore';

export default function ChatPage() {
  const [loading, setLoading] = useState(false);
  // 模型选择相关状态
  const [selectedModel, setSelectedModel] = useState('gpt-3.5-turbo');
  const [selectedProvider, setSelectedProvider] = useState('openai');
  // API 管理模态框状态
  const [isApiKeyModalOpen, setIsApiKeyModalOpen] = useState(false);

  const { token } = theme.useToken();
  const { isDarkMode } = useAppTheme();
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // 使用聊天存储
  const {
    sessions,
    chatMessages: rawChatMessages,
    activeSessionId,
    createSession,
    sendMessage,
    updateMessage,
    switchSession,
    deleteSession,
    updateSessionTitle,
  } = useChatStore();

  // 确保 chatMessages 是一个 Map 对象
  const chatMessages = rawChatMessages && typeof rawChatMessages.get === 'function' 
    ? rawChatMessages 
    : new Map();

  // 确保有一个活跃会话
  useEffect(() => {
    if (!activeSessionId && sessions.length === 0) {
      createSession();
    }
  }, [activeSessionId, sessions.length, createSession]);

  // 获取当前会话的消息
  const currentMessages = activeSessionId && chatMessages && typeof chatMessages.get === 'function' 
    ? chatMessages.get(activeSessionId) || [] 
    : [];

  // 处理模型选择变化
  const handleModelChange = (modelId: string, provider: string) => {
    setSelectedModel(modelId);
    setSelectedProvider(provider);
  };

  // 打开 API 管理模态框
  const handleOpenSettings = () => {
    setIsApiKeyModalOpen(true);
  };

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [currentMessages, loading]);

  const handleSend = async (text: string, contextItems: SearchResultItem[]) => {
    if (!text.trim() && contextItems.length === 0) return;
    if (!activeSessionId) return;

    // 1. UI 消息构建
    // 创建 userMessage
    const userMessage = {
      id: uuidv4(),
      role: 'user' as const,
      content: text, // 仅存放纯文本，保持界面整洁
      createdAt: new Date(),
      extra: { contextItems } // 将 contextItems 存入 extra 字段，用于元数据持久化
    };

    // 添加用户消息到存储中
    sendMessage(activeSessionId, userMessage);

    // 2. 后端 Payload 构建 (RAG)
    // 准备格式化的消息
    const formattedMessages = [
      ...currentMessages.map((msg: Message) => ({
        role: msg.role,
        content: msg.content
      }))
    ];

    // 构建用户消息
    let userContent = text;
    if (contextItems.length > 0) {
      // 将 contextItems 格式化为 XML 字符串
      const contextXml = contextItems.map(item => {
        return `<Entity id="${item.id}" source="${item.source}" sourceId="${item.sourceId}">${item.title}</Entity>`;
      }).join('\n');
      
      // 将格式化后的 Context 拼接到 Prompt 中
      userContent = `Context:\n${contextXml}\n\nUser Question:\n${text}`;
    }
    
    formattedMessages.push({ role: 'user', content: userContent });

    // 3. 请求发送
    try {
      // 开始加载状态
      setLoading(true);
      
      // 为 AI 回复创建一个占位消息
      const aiMessageId = uuidv4();
      const aiMessage = {
        id: aiMessageId,
        role: 'assistant' as const,
        content: '',
        createdAt: new Date()
      };
      sendMessage(activeSessionId, aiMessage);

      // Call the backend API
      const response = await chatWithBackend({
        messages: formattedMessages,
        provider: selectedProvider,
        model: selectedModel,
        temperature: 0.7
      });

      if (!response.ok) {
        throw new Error(`API request failed: ${response.status}`);
      }

      // Handle streaming response
      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error('No response body');
      }

      const decoder = new TextDecoder();
      let accumulatedContent = '';

      // Stream the response
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        accumulatedContent += chunk;

        // Update the AI message with the accumulated content
        updateMessage(activeSessionId, accumulatedContent, aiMessageId);
      }
    } catch (error) {
      console.error('Error sending message:', error);
      
      // Update the AI message with the error content
      updateMessage(activeSessionId, `Error: ${error instanceof Error ? error.message : 'Unknown error'}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div 
      className="flex-1 flex min-h-0 w-full relative overflow-hidden"
      style={{ background: 'transparent' }} 
    >
      {/* 侧边栏：会话列表 */}
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
          {/* 侧边栏标题和新建按钮 */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <h3 style={{ margin: 0, fontSize: 16, fontWeight: 'bold' }}>会话</h3>
            <ActionIcon 
              icon={Plus} 
              title="新建会话" 
              onClick={createSession}
              style={{ cursor: 'pointer' }}
            />
          </div>

          {/* 会话列表 */}
          <div style={{ flex: 1, overflowY: 'auto', gap: 8, display: 'flex', flexDirection: 'column' }}>
            {sessions.map((session) => (
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
                onClick={() => switchSession(session.id)}
              >
                <div style={{ flex: 1, marginRight: 8 }}>
                  <div style={{ fontWeight: '500', fontSize: 14, marginBottom: 4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {session.title}
                  </div>
                  <div style={{ fontSize: 12, color: isDarkMode ? '#9ca3af' : '#6b7280' }}>
                    {new Date(session.updatedAt).toLocaleString()}
                  </div>
                </div>
                <ActionIcon 
                  icon={Trash2} 
                  title="删除会话" 
                  size={16}
                  onClick={(e) => {
                    e.stopPropagation();
                    deleteSession(session.id);
                  }}
                  style={{ color: isDarkMode ? '#ef4444' : '#dc2626', cursor: 'pointer' }}
                />
              </div>
            ))}

            {/* 空会话提示 */}
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

      {/* 主聊天区域 */}
      <div className="flex-1 flex flex-col min-h-0 relative overflow-hidden">
        <div 
          className="flex-1 overflow-y-auto p-4"
          style={{ paddingBottom: 200 }} 
        >
          <div className="max-w-3xl mx-auto space-y-6">
            
              {currentMessages.map((msg: Message) => (
                <>
                  <ChatItem
                    key={msg.id}
                    placement={msg.role === 'user' ? 'right' : 'left'}
                    message={msg.content}
                    time={msg.createdAt instanceof Date ? msg.createdAt.getTime() : Number(msg.createdAt)}
                    
                    // 使用图标作为头像，避免 Image 组件警告
                    avatar={{ 
                      title: msg.role === 'user' ? '用户' : 'OtakuNeko',
                      avatar: '/Icon.png',
                    }}
                    
                    avatarProps={{
                    size: 40,
                    style: {
                      // 🛑 绝对不要写 'pixelated' 或 'crisp-edges' (那是给像素画用的)
                      // ✅ 强制浏览器使用平滑算法 (Bilinear/Bicubic)
                      imageRendering: 'auto', 
                      
                      // ✅ 某些浏览器 (如 Chrome) 在极度缩小图片时需要这个属性来开启抗锯齿
                      WebkitFontSmoothing: 'antialiased', 
                      
                      // ✅ 确保图片填满圆形且不变形
                      objectFit: 'cover',
                      
                      // 保持之前的背景色逻辑
                      backgroundColor: msg.role === 'user' ? token.colorWarning : undefined,
                    }
                  }}
                  />
                  
                  {/* 添加引用胶囊，作为ChatItem的兄弟元素 */}
                  {msg.role === 'user' && msg.extra?.contextItems?.length > 0 && (
                    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 8, justifyContent: 'flex-end' }}>
                      {msg.extra.contextItems.map((ref: any) => (
                        <div
                          key={ref.id}
                          style={{
                            display: 'flex', alignItems: 'center', gap: 4,
                            fontSize: 12, padding: '4px 8px', borderRadius: 12,
                            background: isDarkMode ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.05)',
                            color: isDarkMode ? 'rgba(255,255,255,0.8)' : 'rgba(0,0,0,0.6)',
                          }}
                        >
                          <img src={ref.cover} alt={ref.title} style={{ width: 16, height: 16, borderRadius: '50%', objectFit: 'cover' }} />
                          <span>{ref.title}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </>
              ))}

              {/* 修复：只有当消息列表最后一条不是 assistant 角色时，才显示 Loading 气泡 */}
              {loading && currentMessages.length > 0 && currentMessages[currentMessages.length - 1].role !== 'assistant' && (
                <ChatItem
                  placement="left"
                  loading={true}
                  
                  // 使用图标作为头像，避免 Image 组件警告
                  avatar={{ 
                    title: 'OtakuNeko',
                    avatar: '/Icon.png',
                  }}
                  
                  avatarProps={{
                    size: 40,
                  }}
                />
              )}

              <div ref={messagesEndRef} />
            </div>
          </div>

          <ChatInput
            onSend={handleSend}
            loading={loading}
            selectedModel={selectedModel}
            selectedProvider={selectedProvider}
            onModelChange={handleModelChange}
            onOpenSettings={handleOpenSettings}
          />

          {/* API Key 管理模态框 */}
          <ApiKeyModal
            open={isApiKeyModalOpen}
            onClose={() => setIsApiKeyModalOpen(false)}
          />
        </div>
      </div>
  );
}