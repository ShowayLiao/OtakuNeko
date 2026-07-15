"use client";

import { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import {
  BrainCircuit, ChevronRight, Loader2, CheckCircle2, Wrench,
} from 'lucide-react';
import type { ProcessNode } from '@/stores/useChatStore';
import ProcessStepItem from './ProcessStepItem';

interface ProcessContainerProps {
  processes: ProcessNode[];
  plan?: string;
  isStreaming: boolean;
  isDarkMode: boolean;
  onRetryTool?: (node: ProcessNode) => void;
}

export default function ProcessContainer({
  processes,
  plan,
  isStreaming,
  isDarkMode,
  onRetryTool,
}: ProcessContainerProps) {
  const [expanded, setExpanded] = useState(false);
  const userToggledRef = useRef(false);
  const prevStreamingRef = useRef(isStreaming);
  const listEndRef = useRef<HTMLDivElement>(null);
  const innerRef = useRef<HTMLDivElement>(null);

  const allDone = processes.length > 0 && processes.every(
    p => p.status === 'success' || p.status === 'error'
  );
  const hasRunning = processes.some(p => p.status === 'pending');
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

  const showLabel = statusLabel || suffixParts.length > 0;
  const summaryText = showLabel
    ? [statusLabel, ...suffixParts].filter(Boolean).join(' · ')
    : '';

  const statusIcon = useMemo(() => {
    if (hasRunning) {
      return <Loader2 size={14} className="animate-spin" style={{ color: isDarkMode ? '#a5b4fc' : '#6366f1' }} />;
    }
    if (allDone) {
      return <CheckCircle2 size={14} style={{ color: isDarkMode ? '#86efac' : '#15803d' }} />;
    }
    return <BrainCircuit size={14} style={{ color: isDarkMode ? '#a5b4fc' : '#6366f1' }} />;
  }, [hasRunning, allDone, isDarkMode]);

  useEffect(() => {
    if (!prevStreamingRef.current && isStreaming && !userToggledRef.current) {
      setExpanded(true);
    }

    if (prevStreamingRef.current && !isStreaming && !userToggledRef.current && allDone) {
      setExpanded(false);
    }

    prevStreamingRef.current = isStreaming;
  }, [isStreaming, allDone]);

  useEffect(() => {
    if (expanded && listEndRef.current) {
      listEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [processes, expanded]);

  const toggle = useCallback(() => {
    userToggledRef.current = true;
    setExpanded(prev => !prev);
  }, []);

  if (processes.length === 0 && !plan) return null;

  const chevronStyle: React.CSSProperties = {
    transform: expanded ? 'rotate(90deg)' : 'rotate(0deg)',
    transition: 'transform 0.15s',
  };

  return (
    <div
      style={{
        borderRadius: 10,
        background: isDarkMode ? 'rgba(99,102,241,0.05)' : 'rgba(99,102,241,0.03)',
        border: `1px solid ${isDarkMode ? 'rgba(99,102,241,0.12)' : 'rgba(99,102,241,0.1)'}`,
        overflow: 'hidden',
      }}
    >
      <div
        onClick={toggle}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          padding: '8px 12px',
          cursor: 'pointer',
          userSelect: 'none',
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
        <ChevronRight size={14} style={{ color: isDarkMode ? '#9ca3af' : '#6b7280', ...chevronStyle }} />
      </div>

      <div
        ref={innerRef}
        style={{
          display: 'grid',
          gridTemplateRows: expanded ? '1fr' : '0fr',
          transition: 'grid-template-rows 0.3s ease',
        }}
      >
        <div style={{ overflow: 'hidden' }}>
          <div style={{
            borderTop: `1px solid ${isDarkMode ? 'rgba(99,102,241,0.08)' : 'rgba(99,102,241,0.06)'}`,
            padding: '8px 12px 12px',
            display: 'flex',
            flexDirection: 'column',
            gap: 8,
            maxHeight: 360,
            overflowY: 'auto',
          }}>
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
                isStreaming={isStreaming}
                onRetry={onRetryTool}
              />
            ))}

            <div ref={listEndRef} />
          </div>
        </div>
      </div>
    </div>
  );
}
