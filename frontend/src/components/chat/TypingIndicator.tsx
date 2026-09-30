"use client";

import { Loader2 } from 'lucide-react';
import { useAppTheme } from '@/components/providers/LobeProvider';

export default function TypingIndicator() {
  const { isDarkMode } = useAppTheme();

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 6,
        padding: '8px 0',
      }}
    >
      <Loader2
        size={16}
        className="animate-spin"
        style={{ color: isDarkMode ? '#93c5fd' : '#3b82f6' }}
      />
      <span
        style={{
          fontSize: 13,
          color: isDarkMode ? '#9ca3af' : '#6b7280',
        }}
      >
        正在思考...
      </span>
    </div>
  );
}
