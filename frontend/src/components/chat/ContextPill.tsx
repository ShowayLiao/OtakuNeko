"use client";

import { X } from 'lucide-react';
import { ActionIcon, Avatar } from '@lobehub/ui';

interface ContextPillProps {
  item: {
    id: string;
    title: string;
    cover?: string;
  };
  darkMode?: boolean;
  onRemove?: () => void;
  onClick?: () => void;
}

export default function ContextPill({ item, darkMode = false, onRemove, onClick }: ContextPillProps) {
  return (
    <div
      title={item.title}
      onClick={onClick}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 6,
        padding: '6px 12px',
        borderRadius: 16,
        backgroundColor: darkMode ? 'rgba(75, 85, 99, 0.4)' : 'rgba(229, 231, 235, 0.6)',
        border: `1px solid ${darkMode ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.05)'}`,
        backdropFilter: 'saturate(180%) blur(12px)',
        cursor: onClick ? 'pointer' : 'default',
        transition: 'all 0.2s ease',
      }}
    >
      <Avatar size={24} avatar={item.cover || '/Icon.png'} />
      <span style={{ fontSize: 12, fontWeight: 500 }}>{item.title}</span>
      {onRemove && (
        <ActionIcon
          icon={X}
          size={{ blockSize: 14 }}
          onClick={(e: React.MouseEvent) => { e.stopPropagation(); onRemove(); }}
        />
      )}
    </div>
  );
}
