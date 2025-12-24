"use client";

import React from 'react';
import { Paperclip } from 'lucide-react';

interface MessageAttachmentProps {
  name: string;
}

export const MessageAttachment: React.FC<MessageAttachmentProps> = ({ name }) => {
  return (
    <div className="bg-white/20 rounded-md border-l-4 border-white/50 p-2 flex items-center gap-2 mb-2">
      <Paperclip className="h-3 w-3 text-white/90" />
      <span className="font-medium text-sm text-white/90">{name}</span>
    </div>
  );
};
