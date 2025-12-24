"use client";

import { createContext, useContext, useState, ReactNode } from 'react';
import { Subject } from '@/lib/api';

interface ChatContextType {
  referenceItem: Subject | null;
  setReferenceItem: (item: Subject | null) => void;
}

const ChatContext = createContext<ChatContextType | undefined>(undefined);

export const ChatProvider = ({ children }: { children: ReactNode }) => {
  const [referenceItem, setReferenceItem] = useState<Subject | null>(null);

  return (
    <ChatContext.Provider value={{ referenceItem, setReferenceItem }}>
      {children}
    </ChatContext.Provider>
  );
};

export const useChatContext = () => {
  const context = useContext(ChatContext);
  if (context === undefined) {
    throw new Error('useChatContext must be used within a ChatProvider');
  }
  return context;
};
