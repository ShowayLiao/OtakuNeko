"use client";

import { useState, useRef, useEffect } from 'react';
// 1. 引入图标并重命名，防止命名冲突
import { Eraser, Languages, User as UserIcon, Bot as BotIcon } from 'lucide-react';
import { theme } from 'antd';
import { ChatInputArea, ChatInputActionBar, TokenTag, ChatItem, ChatSendButton } from '@lobehub/ui/chat';
import { ActionIcon } from '@lobehub/ui';
import { useAppTheme } from '@/components/providers/LobeProvider';
import { ModelSelector } from './ModelSelector';
import SearchTrigger from './SearchBar';
import ApiKeyModal from '../Modal/ApiKeyModal';
import { chatWithBackend } from '@/lib/fetcher';

// --- 2. 定义消息数据结构 ---
interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  createAt: number;
}

const MOCK_RESPONSES = [
  "收到！正在为你分析这段代码...",
  "根据量子力学，薛定谔的猫现在可能在吃罐头。🐱",
  "这个问题很有趣，我们需要从架构层面来重新思考。",
  "系统检测到您的颜值过高，已自动开启高性能模式！🚀",
  "正在调用 OtakuNeko 的神经网络...",
  "请稍等，我正在查阅开发文档。",
  "代码看起来没问题，建议检查一下环境变量配置。",
];

export default function ChatPage() {
  const [isExpand, setIsExpand] = useState(false);
  const [value, setValue] = useState('');
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'init-1',
      role: 'assistant',
      content: '你好！我是 OtakuNeko，今天想聊点什么？😸',
      createAt: Date.now(),
    }
  ]);
  // 模型选择相关状态
  const [selectedModel, setSelectedModel] = useState('gpt-3.5-turbo');
  const [selectedProvider, setSelectedProvider] = useState('openai');
  // API 管理模态框状态
  const [isApiKeyModalOpen, setIsApiKeyModalOpen] = useState(false);
  const heights = {
    inputHeight: 160, 
    minHeight: 128,
    maxHeight: 600, 
  };

  const { token } = theme.useToken();
  const { isDarkMode } = useAppTheme();
  const messagesEndRef = useRef<HTMLDivElement>(null);

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
  }, [messages, loading]);

  const handleSend = async () => {
    if (!value.trim()) return;

    const userMsg: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: value,
      createAt: Date.now(),
    };

    setMessages((prev) => [...prev, userMsg]);
    setValue('');
    setLoading(true);

    try {
      // Create a new AI message with an ID, but empty content for streaming
      const aiMsgId = (Date.now() + 1).toString();
      const aiMsg: Message = {
        id: aiMsgId,
        role: 'assistant',
        content: '',
        createAt: Date.now(),
      };

      setMessages((prev) => [...prev, aiMsg]);

      // Prepare the message format for the backend
      const formattedMessages = [
        ...messages.map(msg => ({
          role: msg.role,
          content: msg.content
        })),
        { role: 'user', content: value }
      ];

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
        setMessages((prev) => prev.map(msg => 
          msg.id === aiMsgId ? { ...msg, content: accumulatedContent } : msg
        ));
      }
    } catch (error) {
      console.error('Error sending message:', error);
      
      // Add an error message to the chat
      const errorMsg: Message = {
        id: (Date.now() + 2).toString(),
        role: 'assistant',
        content: `Error: ${error instanceof Error ? error.message : 'Unknown error'}`,
        createAt: Date.now(),
      };

      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div 
      className="flex-1 flex flex-col min-h-0 w-full relative overflow-hidden"
      style={{ background: 'transparent' }} 
    >
      <div 
        className="flex-1 overflow-y-auto p-4"
        style={{ paddingBottom: 200 }} 
      >
        <div className="max-w-3xl mx-auto space-y-6">
          
          {messages.map((msg) => (
            <ChatItem
              key={msg.id}
              placement={msg.role === 'user' ? 'right' : 'left'}
              message={msg.content}
              time={msg.createAt}
              
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
          ))}

          {loading && (
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

      <div
        style={{
          position: 'absolute',
          bottom: 0,
          left: 0,
          width: '100%',
          // 🔥 关键点1：外部留白，制造“悬浮”感
          padding: '0 16px 24px 16px', 
          zIndex: 10,
        }}
      >
        <ChatInputArea 
          topAddons={
              <ChatInputActionBar
                leftAddons={
                  <div style={{ marginLeft: '20px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <ModelSelector 
                      value={selectedModel} 
                      onChange={handleModelChange} 
                      onOpenSettings={handleOpenSettings} 
                    />
                    <SearchTrigger />
                    <ActionIcon icon={Languages} title="翻译" />
                    <ActionIcon icon={Eraser} title="清除" />
                    <TokenTag maxValue={5000} value={1000} />
                  </div>
                }
              />
            }
          // ✅ 修复点 1：给发送按钮绑定 handleSend，并绑定 loading 状态
          bottomAddons={<ChatSendButton loading={loading} onSend={handleSend} />}
          
          expand={isExpand}
          setExpand={setIsExpand}
          heights={heights}
          value={value}
          onInput={setValue}
          
          // ✅ 修复点 2：这里必须调用 handleSend，而不是只清空
          // handleSend 内部已经包含了 setValue('') 的逻辑，所以不用重复写
          onSend={handleSend}
          
          placeholder="输入消息..."
          
          // 🔥 关键点2：整容级样式覆盖
          style={{
            // 1. 背景：根据 isDarkMode 手动调教最佳透明度
            //    - 亮色：白色 60% 透明度
            //    - 暗色：深灰 (#1e1e1e) 60% 透明度 (比纯黑更透气)
            background: isDarkMode 
              ? 'rgba(30, 30, 30, 0.6)' 
              : 'rgba(255, 255, 255, 0.6)',

            // 2. 磨砂效果：增加饱和度让背后的色彩更鲜艳
            backdropFilter: 'saturate(180%) blur(12px)',
            
            // 3. 边框：极其微弱的边框，暗色下几乎不可见，亮色下淡淡的灰
            border: `1px solid ${isDarkMode ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.06)'}`,
            
            // 4. 光影魔法：
            //    - 外阴影 (Drop Shadow): 让卡片浮起来
            //    - 内阴影 (Inset Shadow): 模拟玻璃厚度的反光 (顶部高光)
            boxShadow: isDarkMode
              ? '0 8px 32px 0 rgba(0, 0, 0, 0.3), inset 0 1px 0 0 rgba(255, 255, 255, 0.05)'
              : '0 8px 32px 0 rgba(0, 0, 0, 0.08), inset 0 1px 0 0 rgba(255, 255, 255, 0.6)',
            
            borderRadius: 16, // 大圆角
            overflow: 'hidden', // 确保内部内容不溢出圆角
          }}
          className="w-full"
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