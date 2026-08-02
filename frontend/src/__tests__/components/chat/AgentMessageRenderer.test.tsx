import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('@/components/providers/LobeProvider', () => ({
  useAppTheme: () => ({ isDarkMode: false }),
}));

import AgentMessageRenderer, {
  deriveStatus,
} from '@/components/chat/AgentMessageRenderer';
import type { ProcessNode } from '@/stores/useChatStore';

const thoughtPending: ProcessNode = {
  id: 'thought-1', stepNumber: 1, type: 'thought', status: 'pending', title: '推理',
};
const thoughtDone: ProcessNode = {
  id: 'thought-1', stepNumber: 1, type: 'thought', status: 'success', title: '推理',
  details: 'Let me think about this...',
};
const toolPending: ProcessNode = {
  id: 'tool-1', stepNumber: 2, type: 'tool_call', status: 'pending',
  title: '搜索动画', name: 'search_anime_advanced',
};
const toolDone: ProcessNode = {
  id: 'tool-1', stepNumber: 2, type: 'tool_call', status: 'success',
  title: '搜索动画', name: 'search_anime_advanced', duration: 920.39,
  details: { query: 'test' }, output: { results: [] },
};
describe('deriveStatus', () => {
  it('returns "done" when isStreaming is false', () => {
    expect(deriveStatus(true, [toolPending], false)).toBe('done');
    expect(deriveStatus(false, [], false)).toBe('done');
  });

  it('returns "executing" when streaming and has pending tool_call', () => {
    expect(deriveStatus(false, [toolPending], true)).toBe('executing');
  });

  it('returns "thinking" when streaming with thought node', () => {
    expect(deriveStatus(false, [thoughtPending], true)).toBe('thinking');
  });

  it('returns "thinking" when streaming with no content and no processes', () => {
    expect(deriveStatus(false, [], true)).toBe('thinking');
  });

  it('returns "responding" when streaming with content', () => {
    expect(deriveStatus(true, [thoughtDone], true)).toBe('responding');
  });

  it.each([
    ['failed', 'failed'],
    ['cancelled', 'cancelled'],
    ['timeout', 'timeout'],
  ] as const)('keeps %s as a distinct terminal status', (terminalStatus, expected) => {
    expect(deriveStatus(false, [], false, {
      runId: 'run-terminal',
      lastSequence: 4,
      durable: true,
      phase: terminalStatus,
      terminalStatus,
    }, undefined)).toBe(expected);
  });

  it('returns recovering while a durable run has no terminal event', () => {
    expect(deriveStatus(false, [], false, {
      runId: 'run-recovering',
      lastSequence: 4,
      durable: true,
      phase: 'recovering',
      terminalStatus: null,
    }, 'recovering')).toBe('recovering');
  });
});

describe('AgentMessageRenderer', () => {
  const defaultProps = {
    plan: '',
    processes: [] as ProcessNode[],
    isStreaming: false,
    hasContent: false,
    isDarkMode: false,
    children: null as React.ReactNode,
  };

  it('renders nothing when no processes and no content', () => {
    const { container } = render(<AgentMessageRenderer {...defaultProps} />);
    expect(container.querySelector('.flex-col')).toBeDefined();
  });

  it('renders process container when processes are provided', () => {
    render(<AgentMessageRenderer {...defaultProps} processes={[thoughtDone]} />);
    expect(screen.getByText(/思考完毕/)).toBeDefined();
  });

  it('renders plan text in process container', () => {
    render(<AgentMessageRenderer {...defaultProps} plan="第一步搜索" processes={[toolDone]} />);
    expect(screen.getByText(/思考完毕/)).toBeDefined();
  });

  it('shows "正在思考..." during streaming with thought', () => {
    render(
      <AgentMessageRenderer {...defaultProps} processes={[thoughtPending]} isStreaming />
    );
    expect(screen.getAllByText(/正在思考/).length).toBeGreaterThan(0);
  });

  it('shows "正在调用工具..." during streaming with tool', () => {
    render(
      <AgentMessageRenderer {...defaultProps} processes={[toolPending]} isStreaming />
    );
    expect(screen.getByText(/正在调用工具/)).toBeDefined();
  });

  it('renders children when hasContent is true', () => {
    render(
      <AgentMessageRenderer {...defaultProps} hasContent>
        <div data-testid="markdown-content">Hello World</div>
      </AgentMessageRenderer>
    );
    expect(screen.getByTestId('markdown-content')).toBeDefined();
  });

  it('does not render children when hasContent is false', () => {
    render(
      <AgentMessageRenderer {...defaultProps} hasContent={false}>
        <div data-testid="markdown-content">Hello World</div>
      </AgentMessageRenderer>
    );
    expect(screen.queryByTestId('markdown-content')).toBeNull();
  });

  it('keeps the latest completed process details visible before the answer starts', () => {
    render(
      <AgentMessageRenderer {...defaultProps} processes={[thoughtDone]} />
    );
    expect(screen.getByText('Let me think about this...')).toBeDefined();
  });

  it('collapses the latest normal process once the answer starts', () => {
    render(
      <AgentMessageRenderer
        {...defaultProps}
        processes={[thoughtDone]}
        isStreaming
        hasContent
      />
    );
    expect(screen.queryByText('Let me think about this...')).toBeNull();
  });

  it('renders tool duration in process node', () => {
    render(
      <AgentMessageRenderer {...defaultProps} processes={[toolDone]} />
    );
    expect(screen.getByText('搜索动画')).toBeDefined();
  });

  it('renders tool node number badges', () => {
    render(
      <AgentMessageRenderer {...defaultProps} processes={[thoughtDone, toolDone]} />
    );
    const badges = document.querySelectorAll('[style*="border-radius: 10"]');
    expect(badges.length).toBeGreaterThanOrEqual(1);
  });

  it('retains a partial answer with an explicit failed run presentation', () => {
    render(
      <AgentMessageRenderer
        {...defaultProps}
        hasContent
        run={{
          runId: 'run-partial',
          lastSequence: 8,
          durable: true,
          phase: 'failed',
          terminalStatus: 'failed',
          errorCode: 'provider_error',
        }}
      >
        <div data-testid="partial-answer">partial answer</div>
      </AgentMessageRenderer>,
    );

    expect(screen.getByTestId('partial-answer')).toBeDefined();
    expect(screen.getByText(/Run failed/)).toBeDefined();
  });

  it('retains a partial answer with an explicit recovery presentation', () => {
    render(
      <AgentMessageRenderer
        {...defaultProps}
        hasContent
        messageStatus="recovering"
        run={{
          runId: 'run-recovering',
          lastSequence: 8,
          durable: true,
          phase: 'recovering',
          terminalStatus: null,
          errorCode: 'stream_interrupted',
        }}
      >
        <div data-testid="recovering-answer">partial answer</div>
      </AgentMessageRenderer>,
    );

    expect(screen.getByTestId('recovering-answer')).toBeDefined();
    expect(screen.getByText(/Run interrupted/)).toBeDefined();
  });
});
