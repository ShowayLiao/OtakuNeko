"use client";

import React, { useState, useRef, useEffect } from 'react';
import { Send, ChevronDown, ChevronUp, X, Paperclip } from 'lucide-react';
import { useChatContext } from '@/contexts/ChatContext';

interface ChatInputProps {
  onSendMessage: (message: string) => void;
}

// 模型类型定义
interface Model {
  id: string;
  name: string;
}

// Role类型定义
interface Role {
  id: string;
  name: string;
}

export const ChatInput: React.FC<ChatInputProps> = ({ onSendMessage }) => {
  const [message, setMessage] = useState('');
  const [isModelOpen, setIsModelOpen] = useState(false);
  const [isRoleOpen, setIsRoleOpen] = useState(false);
  const [selectedModel, setSelectedModel] = useState<Model>({
    id: 'deepseek',
    name: 'Deepseek'
  });
  const [selectedRole, setSelectedRole] = useState<Role>({
    id: 'user',
    name: 'User'
  });
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const modelDropdownRef = useRef<HTMLDivElement>(null);
  const roleDropdownRef = useRef<HTMLDivElement>(null);
  const { referenceItem, setReferenceItem } = useChatContext();

  // 模型列表
  const models: Model[] = [
    { id: 'deepseek', name: 'Deepseek' },
    { id: 'gpt4', name: 'GPT-4' },
    { id: 'claude', name: 'Claude' },
    { id: 'gemini', name: 'Gemini' }
  ];

  // Role列表
  const roles: Role[] = [
    { id: 'user', name: 'User' },
    { id: 'assistant', name: 'Assistant' },
    { id: 'system', name: 'System' },
    { id: 'developer', name: 'Developer' }
  ];

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
    }
  }, [message]);

  // 点击外部关闭下拉菜单
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        modelDropdownRef.current &&
        !modelDropdownRef.current.contains(event.target as Node)
      ) {
        setIsModelOpen(false);
      }
      if (
        roleDropdownRef.current &&
        !roleDropdownRef.current.contains(event.target as Node)
      ) {
        setIsRoleOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (message.trim()) {
      let finalMessage = message.trim();
      
      // 如果有引用上下文，将其信息拼接到消息中
      if (referenceItem) {
        const contextText = `[Context: {"name": "${referenceItem.name_cn || referenceItem.name}", "score": ${(referenceItem.score ?? referenceItem.rating_details?.score ?? referenceItem.rating?.score ?? 0).toFixed(1)}}]\n\n`;
        finalMessage = contextText + finalMessage;
        
        // 发送后清空引用上下文
        setReferenceItem(null);
      }
      
      onSendMessage(finalMessage);
      setMessage('');
    }
  };

  const handleModelSelect = (model: Model) => {
    setSelectedModel(model);
    setIsModelOpen(false);
  };

  const handleRoleSelect = (role: Role) => {
    setSelectedRole(role);
    setIsRoleOpen(false);
  };

  return (
    <div className="bg-white rounded-2xl shadow-xl relative">
      {/* Context Bubble - Shown when referenceItem is selected */}
      {/* 悬浮气泡样式：绝对定位在输入框上方 */}
      {referenceItem && (
        <div className="bg-transparent border border-gray-200 rounded-lg px-3 py-1.5 flex items-center justify-between shadow-sm absolute bottom-full left-0 mb-3 animate-fadeInUp w-fit">
          <div className="flex items-center">
            <Paperclip className="h-3 w-3 mr-1.5 text-gray-500" />
            <div className="font-medium text-sm">{referenceItem.name_cn || referenceItem.name}</div>
          </div>
          <button
            onClick={() => setReferenceItem(null)}
            className="w-6 h-6 rounded-full flex items-center justify-center text-gray-500 hover:bg-gray-100 transition-colors ml-2"
            aria-label="Remove reference"
          >
            <X className="h-3 w-3" />
          </button>
        </div>
      )}
      
      <form
        onSubmit={handleSubmit}
        className="p-4"
      >
        {/* Top Row: Textarea */}
        <textarea
          ref={textareaRef}
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="Type your message..."
          className="w-full resize-none border-none outline-none p-4 bg-gray-50 focus:bg-white transition-colors min-h-[80px] max-h-[200px] overflow-y-auto"
          rows={1}
        />
        
        {/* Bottom Row: Action Bar */}
        <div className="flex items-center justify-between pt-3 border-t border-gray-100 mt-2">
          {/* Left: Role Selector - Expandable Dropdown */}
          <div className="relative" ref={roleDropdownRef}>
            <button
              type="button"
              onClick={() => setIsRoleOpen(!isRoleOpen)}
              className="px-4 py-2 rounded-full border border-gray-300 text-sm font-medium text-gray-700 bg-gray-50 flex items-center gap-2 hover:bg-gray-100 transition-colors"
            >
              {selectedRole.name}
              {isRoleOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </button>
            
            {/* Role Dropdown Menu - 向上展开 */}
            {isRoleOpen && (
              <div className="absolute bottom-full left-0 mb-1 w-48 bg-white rounded-xl shadow-lg border border-gray-200 overflow-hidden z-10">
                {roles.map((role) => (
                  <button
                    key={role.id}
                    type="button"
                    onClick={() => handleRoleSelect(role)}
                    className={`w-full text-left px-4 py-2 text-sm transition-colors ${selectedRole.id === role.id
                      ? 'bg-gray-100 text-gray-900'
                      : 'text-gray-700 hover:bg-gray-50'}
                    `}
                  >
                    {role.name}
                  </button>
                ))}
              </div>
            )}
          </div>
          
          {/* Right Section: Model Selector and Send Button */}
          <div className="flex items-center gap-2">
            {/* Middle: Model Selector - Expandable Dropdown */}
            <div className="relative" ref={modelDropdownRef}>
              <button
                type="button"
                onClick={() => setIsModelOpen(!isModelOpen)}
                className="px-4 py-2 rounded-full border border-gray-300 text-sm font-medium text-gray-700 bg-gray-50 flex items-center gap-2 hover:bg-gray-100 transition-colors"
              >
                {selectedModel.name}
                {isModelOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
              </button>
              
              {/* Model Dropdown Menu - 向上展开 */}
              {isModelOpen && (
                <div className="absolute bottom-full right-0 mb-1 w-48 bg-white rounded-xl shadow-lg border border-gray-200 overflow-hidden z-10">
                  {models.map((model) => (
                    <button
                      key={model.id}
                      type="button"
                      onClick={() => handleModelSelect(model)}
                      className={`w-full text-left px-4 py-2 text-sm transition-colors ${selectedModel.id === model.id
                        ? 'bg-gray-100 text-gray-900'
                        : 'text-gray-700 hover:bg-gray-50'}
                      `}
                    >
                      {model.name}
                    </button>
                  ))}
                </div>
              )}
            </div>
            
            {/* Right: Send Button */}
            <button
              type="submit"
              disabled={!message.trim()}
              className={`w-12 h-12 rounded-full flex items-center justify-center transition-all duration-200 ${message.trim()
                ? 'bg-primary text-white shadow-md hover:shadow-lg hover:scale-105 hover:bg-primary/90'
                : 'bg-gray-200 text-gray-400 cursor-not-allowed'}
              `}
            >
              <Send className="h-5 w-5" />
            </button>
          </div>
        </div>
      </form>
    </div>
  );
};
