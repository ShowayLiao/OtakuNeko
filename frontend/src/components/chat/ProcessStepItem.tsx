"use client";

import { useState } from 'react';
import {
  Loader2, CheckCircle2, XCircle, ChevronRight, Wrench,
  BrainCircuit, RotateCcw, Clock,
} from 'lucide-react';
import type { ProcessNode } from '@/stores/useChatStore';

interface ProcessStepItemProps {
  node: ProcessNode;
  stepNumber: number;
  isDarkMode: boolean;
  isStreaming: boolean;
  onRetry?: (node: ProcessNode) => void;
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

export default function ProcessStepItem({
  node,
  stepNumber,
  isDarkMode,
  isStreaming,
  onRetry,
}: ProcessStepItemProps) {
  const [expanded, setExpanded] = useState(false);

  const isPending = node.status === 'pending';
  const isError = node.status === 'error';
  const isSuccess = node.status === 'success';
  const isThought = node.type === 'thought';

  const hasBody =
    (node.details != null) ||
    (node.output != null) ||
    (isThought && node.details != null);

  return (
    <div style={{ display: 'flex', gap: 8 }}>
      <div style={{
        width: 20,
        height: 20,
        borderRadius: 10,
        background: isThought
          ? (isDarkMode ? 'rgba(168,85,247,0.3)' : 'rgba(168,85,247,0.2)')
          : (isDarkMode ? 'rgba(59,130,246,0.2)' : 'rgba(59,130,246,0.15)'),
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        flexShrink: 0,
        marginTop: 2,
        fontSize: 10,
        fontWeight: 600,
        color: isThought
          ? (isDarkMode ? '#d8b4fe' : '#7c3aed')
          : (isDarkMode ? '#93c5fd' : '#2563eb'),
      }}>
        {stepNumber}
      </div>

      <div style={{ flex: 1, minWidth: 0 }}>
        {node.reason && (
          <div style={{
            fontSize: 10,
            color: isDarkMode ? '#9ca3af' : '#6b7280',
            paddingLeft: 2,
            marginBottom: 4,
            fontStyle: 'italic',
          }}>
            {node.reason}
          </div>
        )}

        <div
          style={{
            borderRadius: 8,
            background: isError
              ? (isDarkMode ? 'rgba(239,68,68,0.06)' : 'rgba(239,68,68,0.04)')
              : (isDarkMode ? 'rgba(255,255,255,0.03)' : 'rgba(0,0,0,0.02)'),
            border: `1px solid ${
              isError
                ? (isDarkMode ? 'rgba(239,68,68,0.2)' : 'rgba(239,68,68,0.15)')
                : (isDarkMode ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)')
            }`,
            overflow: 'hidden',
          }}
        >
          <div
            onClick={() => !isPending && hasBody && setExpanded(!expanded)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              padding: '8px 10px',
              cursor: isPending || !hasBody ? 'default' : 'pointer',
              userSelect: 'none',
            }}
          >
            {isPending ? (
              <Loader2 size={14} className="animate-spin" style={{ color: isDarkMode ? '#fbbf24' : '#d97706' }} />
            ) : isSuccess ? (
              <CheckCircle2 size={14} style={{ color: isDarkMode ? '#86efac' : '#15803d' }} />
            ) : isError ? (
              <XCircle size={14} style={{ color: isDarkMode ? '#fca5a5' : '#ef4444' }} />
            ) : (
              isThought
                ? <BrainCircuit size={14} style={{ color: isDarkMode ? '#a78bfa' : '#7c3aed' }} />
                : <Wrench size={14} style={{ color: isDarkMode ? '#9ca3af' : '#6b7280' }} />
            )}

            <span style={{
              flex: 1,
              fontSize: 12,
              fontWeight: 500,
              color: isDarkMode ? '#d1d5db' : '#374151',
            }}>
              {isPending
                ? (isThought ? '正在思考...' : `正在调用 ${node.title}...`)
                : node.title}
            </span>

            {node.duration != null && node.duration > 0 && (
              <span style={{
                display: 'flex',
                alignItems: 'center',
                gap: 3,
                fontSize: 10,
                color: isDarkMode ? '#9ca3af' : '#6b7280',
                flexShrink: 0,
              }}>
                <Clock size={10} />
                {formatDuration(node.duration)}
              </span>
            )}

            {isError && onRetry && (
              <button
                onClick={(e) => { e.stopPropagation(); onRetry(node); }}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 3,
                  fontSize: 11,
                  color: isDarkMode ? '#93c5fd' : '#3b82f1',
                  cursor: 'pointer',
                  flexShrink: 0,
                  padding: '2px 6px',
                  borderRadius: 4,
                  border: 'none',
                  background: isDarkMode ? 'rgba(59,130,246,0.1)' : 'rgba(59,130,246,0.06)',
                }}
              >
                <RotateCcw size={10} />
                重试
              </button>
            )}

            {hasBody && !isPending && (
              <ChevronRight
                size={14}
                style={{
                  color: isDarkMode ? '#9ca3af' : '#6b7280',
                  transform: expanded ? 'rotate(90deg)' : 'rotate(0deg)',
                  transition: 'transform 0.15s',
                }}
              />
            )}
          </div>

          {expanded && (
            <div style={{
              borderTop: `1px solid ${isDarkMode ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.06)'}`,
              padding: '8px 10px',
            }}>
              {isThought && node.details != null && (
                <div>
                  <div style={{
                    fontSize: 12,
                    color: isDarkMode ? '#d1d5db' : '#374151',
                    lineHeight: 1.6,
                    whiteSpace: 'pre-wrap',
                  }}>
                    {typeof node.details === 'string' ? node.details : JSON.stringify(node.details, null, 2)}
                  </div>
                </div>
              )}

              {!isThought && node.details != null && (
                <div style={{ marginBottom: node.output != null ? 8 : 0 }}>
                  <div style={{ fontSize: 10, fontWeight: 600, color: isDarkMode ? '#9ca3af' : '#6b7280', marginBottom: 4 }}>
                    输入参数
                  </div>
                  <pre style={{
                    fontSize: 11,
                    overflowX: 'auto',
                    background: isDarkMode ? 'rgba(0,0,0,0.3)' : 'rgba(0,0,0,0.03)',
                    padding: 6,
                    borderRadius: 4,
                    fontFamily: 'monospace',
                    whiteSpace: 'pre-wrap',
                    color: isDarkMode ? '#d1d5db' : '#374151',
                    margin: 0,
                    maxHeight: 120,
                    overflowY: 'auto',
                  }}>
                    {typeof node.details === 'string' ? node.details : JSON.stringify(node.details, null, 2)}
                  </pre>
                </div>
              )}

              {!isThought && node.output != null && (
                <div>
                  <div style={{ fontSize: 10, fontWeight: 600, color: isDarkMode ? '#9ca3af' : '#6b7280', marginBottom: 4 }}>
                    返回结果
                  </div>
                  <pre style={{
                    fontSize: 11,
                    overflowX: 'auto',
                    background: isDarkMode ? 'rgba(0,0,0,0.3)' : 'rgba(0,0,0,0.03)',
                    padding: 6,
                    borderRadius: 4,
                    fontFamily: 'monospace',
                    whiteSpace: 'pre-wrap',
                    color: isDarkMode ? '#d1d5db' : '#374151',
                    margin: 0,
                    maxHeight: 200,
                    overflowY: 'auto',
                  }}>
                    {typeof node.output === 'string' ? node.output : JSON.stringify(node.output, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
