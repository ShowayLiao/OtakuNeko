"use client";

import { useState, useEffect, useRef } from 'react';
import { MessageBubble } from '@/components/chat/MessageBubble';
import { ChatInput } from '@/components/chat/ChatInput';
import { EmptyState } from '@/components/chat/EmptyState';
import { Header } from '@/components/layout/Header';
import { useSync } from '@/hooks/useSync';
import { ChatProvider } from '@/contexts/ChatContext';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
}

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  
  // Use the sync hook for stats and sync functionality
  const { totalItems, fetchCollectionCounts } = useSync();

  // Initialize data on mount
  useEffect(() => {
    fetchCollectionCounts();
  }, []);

  // Scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSendMessage = (content: string) => {
    // Add user message
    const userMessage: Message = {
      id: `user-${Date.now()}`,
      role: 'user',
      content,
      timestamp: new Date().toLocaleTimeString(),
    };

    setMessages(prev => [...prev, userMessage]);

    // Simulate assistant response after 1 second
    setTimeout(() => {
      const assistantResponses = [
        '好的，我来帮你找一下相关的动画资源。',
        '这个作品我很熟悉呢，让我为你详细介绍一下。',
        '根据你的喜好，我推荐你看这部动画。',
        '需要我帮你查询这部作品的评分和评价吗？',
        '我可以帮你安排观看计划，需要吗？',
      ];
      
      const randomResponse = assistantResponses[Math.floor(Math.random() * assistantResponses.length)];
      
      const assistantMessage: Message = {
        id: `assistant-${Date.now()}`,
        role: 'assistant',
        content: randomResponse,
        timestamp: new Date().toLocaleTimeString(),
      };

      setMessages(prev => [...prev, assistantMessage]);
    }, 1000);
  };

  return (
    <ChatProvider>
      <div className="flex flex-col h-screen bg-gray-50">
        {/* Header */}
        <Header />

        {/* Main Content */}
        <main className="flex-1 p-4 lg:p-6">
          {totalItems === 0 ? (
            // Empty State - Show when no subjects are synced
            <EmptyState />
          ) : (
            // Chat Area - Show when subjects are synced
            <div className="flex flex-col w-full max-w-5xl mx-auto">
              {/* Message List */}
              <div className="flex-1 min-h-[300px]">
                {messages.length === 0 ? (
                  // Empty Chat State
                  <div className="flex flex-col items-center justify-center h-full text-center py-12">
                    <img src="/Icon.png" alt="AI" className="w-32 h-32 mb-4 object-contain" />
                    <h2 className="text-2xl font-bold text-gray-900 mb-2">Welcome to OtakuNeko!</h2>
                    <p className="text-gray-600 max-w-md">Type a chat, alert, and allows to rerolce!</p>
                  </div>
                ) : (
                  // Message List
                  <div className="space-y-4">
                    {messages.map(message => (
                      <MessageBubble
                        key={message.id}
                        role={message.role}
                        content={message.content}
                        timestamp={message.timestamp}
                      />
                    ))}
                    <div ref={messagesEndRef} />
                  </div>
                )}
              </div>
            </div>
          )}
        </main>

        {/* Bottom Interaction Area - Only show when subjects are synced */}
        {totalItems > 0 && (
          <div className="p-4 lg:p-6">
            <div className="flex gap-4 items-end max-w-5xl mx-auto">
              {/* Chat Input */}
              <div className="flex-1">
                <ChatInput onSendMessage={handleSendMessage} />
              </div>
            </div>
          </div>
        )}
      </div>
    </ChatProvider>
  );
}
