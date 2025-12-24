"use client";

import React from 'react';
import { MessageAttachment } from './MessageAttachment';

interface MessageBubbleProps {
  role: 'user' | 'assistant';
  content: string;
  timestamp?: string;
}

interface ContextData {
  name: string;
  [key: string]: unknown;
}

export const MessageBubble: React.FC<MessageBubbleProps> = ({ role, content, timestamp }) => {
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

  const { context, cleanedContent } = parseContext(content);

  return (
    <div className={`flex items-end gap-4 mb-4 ${isUser ? 'flex-row-reverse' : 'flex-row'}`}>
      {/* Avatar */}
      {!isUser && (
        <div className="w-25 h-25 rounded-2xl overflow-hidden flex items-center justify-center bg-gray-100">
          <img src="/Icon.png" alt="AI" width={40} height={40} className="w-full h-full object-cover" />
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
            ? 'bg-[#FF8E72] text-white rounded-br-none'
            : 'bg-gray-100 text-gray-900 rounded-bl-none'}
          `}
        >
          {/* Render attachment if context exists */}
          {context && <MessageAttachment name={context.name} />}
          
          {/* Render cleaned message content */}
          <div className="whitespace-pre-wrap">{cleanedContent}</div>
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
