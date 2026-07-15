"use client";

import type { ProcessNode } from '@/stores/useChatStore';
import ProcessContainer from './ProcessContainer';
import FinalAnswerBlock from './FinalAnswerBlock';

export type AgentStatus = 'idle' | 'thinking' | 'executing' | 'responding' | 'done';

interface AgentMessageRendererProps {
  plan: string;
  processes: ProcessNode[];
  isStreaming: boolean;
  hasContent: boolean;
  isDarkMode: boolean;
  children: React.ReactNode;
  onRetryTool?: (node: ProcessNode) => void;
}

export function deriveStatus(
  hasContent: boolean,
  processes: ProcessNode[],
  isStreaming: boolean,
): AgentStatus {
  if (!isStreaming) return 'done';

  const hasRunning = processes.some(p => p.status === 'pending');
  if (hasRunning && processes.some(p => p.type === 'tool_call' && p.status === 'pending')) {
    return 'executing';
  }
  if (hasRunning) return 'thinking';

  if (hasContent) return 'responding';

  if (!hasContent && processes.length === 0) return 'thinking';

  return 'idle';
}

export default function AgentMessageRenderer({
  plan,
  processes,
  isStreaming,
  hasContent,
  isDarkMode,
  children,
  onRetryTool,
}: AgentMessageRendererProps) {
  return (
    <div className="flex flex-col gap-2">
      <ProcessContainer
        processes={processes}
        plan={plan}
        isStreaming={isStreaming}
        isDarkMode={isDarkMode}
        onRetryTool={onRetryTool}
      />

      <FinalAnswerBlock isStreaming={isStreaming} hasContent={hasContent}>
        {children}
      </FinalAnswerBlock>
    </div>
  );
}
