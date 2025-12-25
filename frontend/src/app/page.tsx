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
  content: string; // Full content for assistant messages
  currentContent: string; // Currently displayed content for typing effect
  status: 'sending' | 'sent' | 'error';
  timestamp: string;
}

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  
  // Use the sync hook for stats and sync functionality
  const { totalItems, fetchCollectionCounts } = useSync();

  // Initialize data on mount
  useEffect(() => {
    const initializeData = async () => {
      setIsLoading(true);
      await fetchCollectionCounts();
      setIsLoading(false);
    };
    initializeData();
  }, []);

  // Scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Helper function to generate assistant response with typing effect
  const generateAssistantResponse = (messageId: string, isRetry: boolean = false) => {
    const assistantResponses = [
      '好的，我来帮你找一下相关的动画资源。',
      '这个作品我很熟悉呢，让我为你详细介绍一下。',
      '根据你的喜好，我推荐你看这部动画。',
      '需要我帮你查询这部作品的评分和评价吗？',
      '我可以帮你安排观看计划，需要吗？',
    ];
    
    const randomResponse = assistantResponses[Math.floor(Math.random() * assistantResponses.length)];
    
    // Typing effect - reveal one character at a time
    let index = 0;
    const typingInterval = setInterval(() => {
      if (index <= randomResponse.length) {
        setMessages(prev => 
          prev.map(msg => 
            msg.id === messageId 
              ? { ...msg, currentContent: randomResponse.substring(0, index) } 
              : msg
          )
        );
        index++;
      } else {
        // Typing complete, update status to sent
        setMessages(prev => 
          prev.map(msg => 
            msg.id === messageId ? { ...msg, content: randomResponse, status: 'sent' } : msg
          )
        );
        clearInterval(typingInterval);
      }
    }, 30); // Adjust typing speed here (ms per character)
  };

  const handleSendMessage = (content: string) => {
    // Add user message
    const userMessage: Message = {
      id: `user-${Date.now()}`,
      role: 'user',
      content,
      currentContent: content,
      status: 'sent',
      timestamp: new Date().toLocaleTimeString(),
    };

    setMessages(prev => [...prev, userMessage]);

    // Simulate assistant response with typing effect
    setTimeout(() => {
      // Create initial message with empty content (typing effect)
      const assistantMessage: Message = {
        id: `assistant-${Date.now()}`,
        role: 'assistant',
        content: '',
        currentContent: '',
        status: 'sending',
        timestamp: new Date().toLocaleTimeString(),
      };

      // Add the message with empty content first
      setMessages(prev => [...prev, assistantMessage]);

      // Generate response with typing effect
      generateAssistantResponse(assistantMessage.id);

    }, 1000);
  };

  // Handle message retry
  const handleRetryMessage = (messageId: string) => {
    // Update message status to sending
    setMessages(prev => 
      prev.map(msg => 
        msg.id === messageId 
          ? { ...msg, status: 'sending', currentContent: '' } 
          : msg
      )
    );

    // Regenerate assistant response with typing effect
    generateAssistantResponse(messageId, true);
  };

  return (
    <div className="flex flex-col h-screen bg-gray-50">
      {/* Header */}
      <Header />

      {/* Main Content */}
      <main className="flex-1 p-4 lg:p-6">
        {isLoading ? (
          // Loading State - Show while checking for synced subjects
          <div className="flex items-center justify-center h-full">
            <div className="w-12 h-12 border-4 border-gray-200 border-t-primary rounded-full animate-spin"></div>
          </div>
        ) : totalItems === 0 ? (
          // Empty State - Show only when loading is complete and no subjects are synced
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
                      currentContent={message.currentContent}
                      status={message.status}
                      timestamp={message.timestamp}
                      onRetry={() => {
                        if (message.role === 'assistant') {
                          handleRetryMessage(message.id);
                        }
                      }}
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
  );
}
