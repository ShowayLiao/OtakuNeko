"use client";

import React from 'react';
import Image from 'next/image';
import { MessageAttachment } from './MessageAttachment';
import { AlertCircle, RefreshCw } from 'lucide-react';

interface MessageBubbleProps {
  role: 'user' | 'assistant';
  content: string;
  currentContent?: string;
  status?: 'sending' | 'sent' | 'error';
  timestamp?: string;
  onRetry?: () => void;
}

interface ContextData {
  name: string;
  [key: string]: unknown;
}

export const MessageBubble: React.FC<MessageBubbleProps> = ({ role, content, currentContent, status = 'sent', timestamp, onRetry }) => {
  const isUser = role === 'user';

  // 解析上下文数据
  const parseContext = (text: string): { context: ContextData | null; cleanedContent: string } => {
    // 检查消息是否以[Context:开头
    if (text.startsWith('[Context: ')) {
      const contextRegex = /\[Context: (\{[^\]]+\})\]/;
      const match = text.match(contextRegex);
      
      if (match && match[1]) {
        try {
          const contextData = JSON.parse(match[1]) as ContextData;
          // 清理掉上下文部分，只保留用户输入的消息
          const cleanedContent = text.replace(contextRegex, '').trim();
          return { context: contextData, cleanedContent };
        } catch (error) {
          console.error('Failed to parse context:', error);
          return { context: null, cleanedContent: text };
        }
      }
    }
    
    return { context: null, cleanedContent: text };
  };

  // 对于助手消息，使用 currentContent 进行打字机效果，否则使用 content
  const displayContent = isUser ? content : (currentContent ?? content);
  const { context, cleanedContent } = parseContext(displayContent);

  return (
    <div className={`flex items-end gap-4 mb-4 ${isUser ? 'flex-row-reverse' : 'flex-row'}`}>
      {/* Avatar */}
      {!isUser && (
        <div className="w-12 h-12 rounded-2xl overflow-hidden flex items-center justify-center bg-gray-100">
          <Image src="/Icon.png" alt="AI" width={40} height={40} className="w-full h-full object-cover" />
        </div>
      )}

      {/* Message content */}
      <div className="flex flex-col max-w-[80%]">
        {/* Name */}
        <div className={`text-xs font-medium mb-1 ${isUser ? 'text-right' : 'text-left'}`}>
          {isUser ? 'You' : 'Assistant'}
        </div>

        {/* Bubble */}
        <div
          className={`p-4 rounded-2xl shadow-sm ${isUser
            ? 'bg-bg-bubble-user text-text-primary rounded-br-none'
            : status === 'error'
            ? 'bg-red-100 text-red-800 rounded-bl-none border border-red-200'
            : 'bg-bg-bubble-assistant text-text-secondary rounded-bl-none'}
          `}
        >
          {/* Render attachment if context exists */}
          {context && <MessageAttachment name={context.name} />}
          
          {/* Render message content based on status */}
          {status === 'error' ? (
            <div className="flex flex-col gap-3">
              <div className="flex items-center gap-2">
                <AlertCircle className="h-4 w-4 text-red-600" />
                <span className="font-medium">发送失败</span>
              </div>
              <div className="text-sm opacity-80 whitespace-pre-wrap">{cleanedContent}</div>
              {onRetry && (
                <button
                  onClick={onRetry}
                  className="flex items-center gap-1.5 text-sm font-medium px-3 py-1.5 rounded-md transition-colors bg-red-600 text-white hover:bg-red-700"
                >
                  <RefreshCw className="h-3.5 w-3.5" />
                  重试
                </button>
              )}
            </div>
          ) : (
            <div className="whitespace-pre-wrap">{cleanedContent}</div>
          )}
        </div>

        {/* Timestamp */}
        {timestamp && (
          <div className={`text-xs text-gray-400 mt-1 ${isUser ? 'text-right' : 'text-left'}`}>
            {timestamp}
          </div>
        )}
      </div>
    </div>
  );
};
