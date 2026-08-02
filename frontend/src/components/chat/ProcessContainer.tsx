"use client";

import { useMemo, useState } from 'react';
import {
  AlertTriangle, BrainCircuit, CheckCircle2, Eye, EyeOff, LoaderCircle,
} from 'lucide-react';
import type { ProcessNode } from '@/stores/useChatStore';
import ProcessStepItem from './ProcessStepItem';

interface ProcessContainerProps {
  processes: ProcessNode[];
  plan?: string;
  isStreaming: boolean;
  hasContent: boolean;
  status?: 'idle' | 'thinking' | 'executing' | 'responding' | 'recovering' | 'done' | 'failed' | 'cancelled' | 'timeout';
  isDarkMode: boolean;
  onRetryTool?: (node: ProcessNode) => void;
}

export default function ProcessContainer({
  processes,
  plan,
  isStreaming,
  hasContent,
  status = 'thinking',
  isDarkMode,
  onRetryTool,
}: ProcessContainerProps) {
  const [processVisible, setProcessVisible] = useState(true);

  const allDone = processes.length > 0 && processes.every(
    p => p.status !== 'pending'
  );
  const hasRunning = processes.some(p => p.status === 'pending');
  const expandable = processes.length > 0 || Boolean(plan);
  const thoughtCount = processes.filter(p => p.type === 'thought').length;
  const toolCount = processes.filter(p => p.type === 'tool_call').length;

  const suffixParts: string[] = [];
  if (thoughtCount > 0) suffixParts.push(`${thoughtCount} 步推理`);
  if (toolCount > 0) suffixParts.push(`${toolCount} 次工具调用`);

  const streamingLabel = hasRunning
    ? (processes.some(p => p.type === 'tool_call' && p.status === 'pending')
      ? '正在调用工具...'
      : '正在思考...')
    : '';

  const statusLabel = allDone && !isStreaming
    ? '思考完毕'
    : streamingLabel || (isStreaming ? '正在思考...' : '');

  const terminalFailure = status === 'failed' || status === 'cancelled' || status === 'timeout';

  const activeStatusLabel = isStreaming
    ? status === 'executing'
      ? '正在调用工具...'
      : status === 'responding'
        ? '正在生成回答...'
        : status === 'idle'
          ? '正在整理结果...'
          : '正在思考...'
    : statusLabel;

  const terminalLabel = status === 'failed'
    ? 'Run failed'
    : status === 'cancelled'
      ? 'Run cancelled'
      : status === 'timeout'
        ? 'Run timed out'
        : '';
  const recoveryLabel = status === 'recovering' ? 'Run interrupted; reconnecting' : '';
  const showLabel = terminalLabel || recoveryLabel || statusLabel || suffixParts.length > 0;
  const summaryText = showLabel
    ? [terminalLabel || recoveryLabel || activeStatusLabel, ...suffixParts].filter(Boolean).join(' · ')
    : '';

  const statusIcon = useMemo(() => {
    if (status === 'recovering') {
      return <AlertTriangle size={14} style={{ color: isDarkMode ? '#fbbf24' : '#b45309' }} />;
    }
    if (isStreaming) {
      return (
        <LoaderCircle
          className="animate-spin motion-reduce:animate-none"
          size={14}
          style={{ color: isDarkMode ? '#a5b4fc' : '#6366f1' }}
        />
      );
    }
    if (allDone) {
      if (terminalFailure) {
        return <AlertTriangle size={14} style={{ color: isDarkMode ? '#fca5a5' : '#dc2626' }} />;
      }
      return <CheckCircle2 size={14} style={{ color: isDarkMode ? '#86efac' : '#15803d' }} />;
    }
    return <BrainCircuit size={14} style={{ color: isDarkMode ? '#a5b4fc' : '#6366f1' }} />;
  }, [allDone, isDarkMode, isStreaming, status, terminalFailure]);

  if (processes.length === 0 && !plan && !isStreaming) return null;

  if (!processVisible) {
    return (
      <button
        type="button"
        onClick={() => setProcessVisible(true)}
        aria-label="显示思考与工具调用过程"
        title="显示思考与工具调用过程"
        style={{
          alignSelf: 'flex-start', display: 'inline-flex', alignItems: 'center', gap: 6,
          padding: '5px 9px', borderRadius: 999,
          border: `1px solid ${isDarkMode ? 'rgba(99,102,241,0.18)' : 'rgba(99,102,241,0.14)'}`,
          background: isDarkMode ? 'rgba(99,102,241,0.06)' : 'rgba(99,102,241,0.04)',
          color: isDarkMode ? '#a5b4fc' : '#6366f1', fontSize: 11, cursor: 'pointer',
        }}
      >
        <Eye size={13} />
        显示过程
      </button>
    );
  }

  return (
    <div style={{ width: '100%', minWidth: 0 }}>
      <div
        role="status"
        style={{
          display: 'flex', alignItems: 'center', gap: 8,
          padding: '4px 2px 8px',
        }}
      >
        {statusIcon}
        <span style={{
          flex: 1,
          fontSize: 12,
          fontWeight: 500,
          color: isDarkMode ? '#c7d2fe' : '#4338ca',
        }}>
          {summaryText || (isStreaming ? '正在思考...' : '思考完毕')}
        </span>
        <button
          type="button"
          onClick={() => setProcessVisible(false)}
          aria-label="隐藏思考与工具调用过程"
          title="隐藏过程"
          style={{
            display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            width: 24, height: 24, padding: 0, border: 'none', borderRadius: 6,
            background: 'transparent', color: isDarkMode ? '#9ca3af' : '#6b7280',
            cursor: 'pointer',
          }}
        >
          <EyeOff size={13} />
        </button>
      </div>

      {expandable && (
        <div
          style={{
            display: 'flex', flexDirection: 'column', gap: 8,
            borderLeft: `1px solid ${isDarkMode ? 'rgba(99,102,241,0.2)' : 'rgba(99,102,241,0.16)'}`,
            padding: '2px 0 4px 12px',
            marginLeft: 8,
          }}
        >
          {plan && (
            <div
              style={{
                fontSize: 11,
                color: isDarkMode ? '#a5b4fc' : '#6366f1',
                lineHeight: 1.5,
                padding: '4px 8px',
                borderRadius: 6,
                background: isDarkMode ? 'rgba(99,102,241,0.08)' : 'rgba(99,102,241,0.04)',
              }}
            >
              <span style={{ fontWeight: 600 }}>计划：</span>
              {plan}
            </div>
          )}

          {processes.map((node, i) => (
            <ProcessStepItem
              key={node.id}
              node={node}
              stepNumber={i + 1}
              isDarkMode={isDarkMode}
              autoExpanded={i === processes.length - 1 && (!hasContent || node.status !== 'success')}
              onRetry={onRetryTool}
            />
          ))}
        </div>
      )}
    </div>
  );
}
