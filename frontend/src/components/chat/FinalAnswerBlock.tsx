"use client";

interface FinalAnswerBlockProps {
  isStreaming: boolean;
  hasContent: boolean;
  terminalStatus?: 'succeeded' | 'failed' | 'cancelled' | 'timeout' | null;
  errorCode?: string | null;
  recovering?: boolean;
  children: React.ReactNode;
}

export default function FinalAnswerBlock({
  isStreaming,
  hasContent,
  terminalStatus,
  errorCode,
  recovering = false,
  children,
}: FinalAnswerBlockProps) {
  if (!hasContent && !isStreaming && !terminalStatus && !recovering) return null;

  if (!hasContent && isStreaming && !terminalStatus && !recovering) return null;

  const terminalLabel = terminalStatus === 'failed'
    ? 'Run failed'
    : terminalStatus === 'cancelled'
      ? 'Run cancelled'
      : terminalStatus === 'timeout'
        ? 'Run timed out'
        : '';
  const recoveryLabel = recovering ? 'Run interrupted; reconnecting' : '';

  return (
    <div className="w-full">
      {(terminalLabel || recoveryLabel) && (
        <div role="status" style={{ fontSize: 12, color: '#b45309', marginBottom: 8 }}>
          {terminalLabel || recoveryLabel}{errorCode ? ` (${errorCode})` : ''}. Partial answer is retained.
        </div>
      )}
      {children}
    </div>
  );
}
