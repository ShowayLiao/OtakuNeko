"use client";

import type { MessageStatus, ProcessNode, RunView } from '@/stores/useChatStore';
import ProcessContainer from './ProcessContainer';
import FinalAnswerBlock from './FinalAnswerBlock';

export type AgentStatus = 'idle' | 'thinking' | 'executing' | 'responding' | 'recovering' | 'done' | 'failed' | 'cancelled' | 'timeout';

interface AgentMessageRendererProps {
  plan: string;
  processes: ProcessNode[];
  isStreaming: boolean;
  hasContent: boolean;
  isDarkMode: boolean;
  run?: RunView;
  messageStatus?: MessageStatus;
  children: React.ReactNode;
  actions?: React.ReactNode;
  onRetryTool?: (node: ProcessNode) => void;
}

export function deriveStatus(
  hasContent: boolean,
  processes: ProcessNode[],
  isStreaming: boolean,
  run?: RunView,
  messageStatus?: MessageStatus,
): AgentStatus {
  if (run?.terminalStatus === 'cancelled' || messageStatus === 'cancelled') return 'cancelled';
  if (run?.terminalStatus === 'timeout' || messageStatus === 'timeout') return 'timeout';
  if (run?.terminalStatus === 'failed' || messageStatus === 'failed' || messageStatus === 'error') return 'failed';
  if (run?.phase === 'recovering' || messageStatus === 'recovering') return 'recovering';
  if (run?.terminalStatus === 'succeeded') return 'done';
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
  actions,
  onRetryTool,
  run,
  messageStatus,
}: AgentMessageRendererProps) {
  const status = deriveStatus(hasContent, processes, isStreaming, run, messageStatus);

  return (
    <div className="flex flex-col gap-2">
      <ProcessContainer
        processes={processes}
        plan={plan}
        isStreaming={isStreaming}
        hasContent={hasContent}
        status={status}
        isDarkMode={isDarkMode}
        onRetryTool={onRetryTool}
      />

      <FinalAnswerBlock
        isStreaming={isStreaming}
        hasContent={hasContent}
        terminalStatus={run?.terminalStatus ?? (run?.phase === 'failed' ? 'failed' : null)}
        errorCode={run?.errorCode}
        recovering={run?.phase === 'recovering' || messageStatus === 'recovering'}
      >
        {children}
      </FinalAnswerBlock>
      {actions}
    </div>
  );
}
