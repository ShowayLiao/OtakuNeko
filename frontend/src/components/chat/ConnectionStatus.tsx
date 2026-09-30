"use client";

import { Activity } from 'lucide-react';
import { useAppTheme } from '@/components/providers/LobeProvider';

interface ConnectionStatusProps {
  status: 'connected' | 'connecting' | 'disconnected';
}

const STATUS_MAP = {
  connected: { color: '#22c55e', label: 'MCP' },
  connecting: { color: '#f59e0b', label: 'MCP' },
  disconnected: { color: '#9ca3af', label: 'MCP' },
};

export default function ConnectionStatus({ status = 'connected' }: ConnectionStatusProps) {
  const { isDarkMode } = useAppTheme();
  const cfg = STATUS_MAP[status];

  return (
    <div
      title={`MCP 连接: ${status}`}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 4,
        padding: '2px 8px',
        borderRadius: 10,
        fontSize: 11,
        fontWeight: 500,
        background: `${cfg.color}18`,
        border: `1px solid ${cfg.color}33`,
        color: cfg.color,
      }}
    >
      <Activity size={10} />
      {cfg.label}
    </div>
  );
}
