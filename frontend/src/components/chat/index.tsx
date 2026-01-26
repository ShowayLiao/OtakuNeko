"use client";

import { useState } from 'react';
import { ChatInputArea, ChatSendButton, ChatInputActionBar } from '@lobehub/ui/chat';
import { ActionIcon } from '@lobehub/ui';
import { Eraser, Languages } from 'lucide-react';
import { TokenTag } from '@lobehub/ui/chat';

// index.tsx (ChatPage)
export default function ChatPage() {
  const [value, setValue] = useState('');
  const [isExpand, setIsExpand] = useState(false);

  const heights = {
    inputHeight: 200, 
    minHeight: 160,
    maxHeight: 600, 
  };

  return (
    // 1. 使用 flex-1 填满 APPLayout 提供的空间
    // 2. 必须加 min-h-0，否则消息列表太长会把整个 Page 撑开
    <div className="flex-1 flex flex-col min-h-0 w-full relative bg-white overflow-hidden">
      
      {/* 消息列表区 */}
      <div 
        className="flex-1 overflow-y-auto p-4"
        style={{ 
          // 只有当输入框是绝对定位（DraggablePanel 默认行为）时，才需要 paddingBottom
          paddingBottom: isExpand ? 0 : heights.inputHeight,
          minHeight: 0 
        }}
      >
        <div className="max-w-3xl mx-auto space-y-4">
          <div className="p-4 bg-gray-100 rounded-lg">
            现在滚动条应该只出现在这个区域了！🚀
          </div>
          {Array.from({ length: 30 }).map((_, i) => (
            <div key={i} className="p-4 border rounded-xl">历史消息内容 {i}</div>
          ))}
        </div>
      </div>

      {/* 输入框组件 */}
      {/* 注意：不要在它上面放 naked text */}
      <ChatInputArea 
        bottomAddons={<ChatSendButton />}
        topAddons={
          <ChatInputActionBar
            leftAddons={
              <>
                <ActionIcon icon={Languages} />
                <ActionIcon icon={Eraser} />
                <TokenTag maxValue={5000} value={1000} />
              </>
            }
          />
        }
        expand={isExpand}
        setExpand={setIsExpand}
        heights={heights}
        value={value}
        onInput={(v) => setValue(v)}
        onSend={() => {
          setValue('');
          setIsExpand(false);
        }}
        placeholder="输入消息..."
        style={{ zIndex: 10 }}
      />
    </div>
  );
}