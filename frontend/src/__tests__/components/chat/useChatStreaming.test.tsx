import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { RunView } from '@/stores/useChatStore';
import useChatStore from '@/stores/useChatStore';

const { chatWithBackendMock, cancelRunMock } = vi.hoisted(() => ({
  chatWithBackendMock: vi.fn(),
  cancelRunMock: vi.fn(),
}));

vi.mock('@/lib/fetcher', () => ({
  chatWithBackend: chatWithBackendMock,
  cancelRun: cancelRunMock,
}));

import { useChatStreaming } from '@/hooks/useChatStreaming';

const runningView: RunView = {
  runId: 'run-hook',
  lastSequence: 1,
  durable: true,
  phase: 'executing',
  terminalStatus: null,
  connectionStatus: 'connected',
  cancelling: false,
};

interface StreamingCallbacks {
  onRunView?: (view: RunView) => void;
  onToolCallEnd?: (id: string, name: string, output: unknown, duration?: number, status?: string, errorCode?: string | null) => void;
  onToolCallStart?: (id: string, name: string, inputs: unknown) => void;
  onMessageChunk?: (chunk: string) => void;
  onError?: (error: string) => void;
  onComplete?: (metadata: { hasDurableRun: boolean; terminalStatus: string | null }) => void;
}

describe('useChatStreaming RunView projection', () => {
  afterEach(() => {
    chatWithBackendMock.mockReset();
    cancelRunMock.mockReset();
    useChatStore.setState({ sessions: [], chatMessages: {}, sessionConfigs: {}, activeSessionId: null });
  });

  it('associates tool terminal events by invocation id and ignores late duplicate end events', async () => {
    chatWithBackendMock.mockImplementation(async (options: StreamingCallbacks) => {
      options.onRunView?.(runningView);
      options.onToolCallEnd?.('inv-1', 'same.capability', { denied: true }, undefined, 'denied', 'permission_denied');
      options.onToolCallStart?.('inv-1', 'same.capability', ['query']);
      options.onToolCallEnd?.('inv-1', 'same.capability', { should: 'not replace' }, 99, 'succeeded', null);
      options.onToolCallStart?.('inv-2', 'same.capability', ['query']);
      options.onToolCallEnd?.('inv-2', 'same.capability', { ok: true }, undefined, 'succeeded', null);
      options.onRunView?.({ ...runningView, lastSequence: 7, phase: 'completed', terminalStatus: 'succeeded' });
      options.onComplete?.({ hasDurableRun: true, terminalStatus: 'succeeded' });
    });
    const sessionId = 'session-hook';
    const messageId = 'message-hook';
    useChatStore.getState().setSessionMessages(sessionId, [{
      id: messageId,
      role: 'assistant',
      content: '',
      createdAt: new Date(),
    }]);

    const { result } = renderHook(() => useChatStreaming({
      selectedProvider: 'deepseek',
      selectedModel: 'model',
      onConnectionStatusChange: vi.fn(),
    }));

    await act(async () => {
      await result.current.startStreaming({
        messages: [],
        temperature: 0.7,
        activeSessionId: sessionId,
        aiMessageId: messageId,
      });
    });

    const processes = useChatStore.getState().chatMessages[sessionId]?.[0]?.processes || [];
    expect(processes).toHaveLength(2);
    expect(processes.map((process) => [process.sourceId, process.status, process.output])).toEqual([
      ['inv-1', 'denied', '{\n  "denied": true\n}'],
      ['inv-2', 'success', '{\n  "ok": true\n}'],
    ]);
  });

  it('requests cancellation for a durable run and waits for run_cancelled', async () => {
    let callbacks: StreamingCallbacks;
    let resolveStream!: () => void;
    chatWithBackendMock.mockImplementation((options: StreamingCallbacks) => {
      callbacks = options;
      options.onRunView?.(runningView);
      options.onMessageChunk?.('partial');
      options.onToolCallStart?.('inv-cancel', 'same.capability', ['query']);
      return new Promise<void>((resolve) => { resolveStream = resolve; });
    });
    cancelRunMock.mockResolvedValue({ cancellation_requested: true });
    const sessionId = 'session-cancel';
    const messageId = 'message-cancel';
    useChatStore.getState().setSessionMessages(sessionId, [{
      id: messageId,
      role: 'assistant',
      content: 'partial',
      createdAt: new Date(),
    }]);

    const { result } = renderHook(() => useChatStreaming({
      selectedProvider: 'deepseek',
      selectedModel: 'model',
      onConnectionStatusChange: vi.fn(),
    }));

    act(() => {
      void result.current.startStreaming({
        messages: [],
        temperature: 0.7,
        activeSessionId: sessionId,
        aiMessageId: messageId,
      });
    });
    await act(async () => {
      await Promise.resolve();
      result.current.stopGeneration();
      await Promise.resolve();
    });

    expect(cancelRunMock).toHaveBeenCalledWith('run-hook');
    expect(result.current.cancelling).toBe(true);

    await act(async () => {
      callbacks.onRunView?.({
        ...runningView,
        lastSequence: 3,
        phase: 'cancelled',
        terminalStatus: 'cancelled',
      });
      callbacks.onComplete?.({ hasDurableRun: true, terminalStatus: 'cancelled' });
      resolveStream();
      await Promise.resolve();
    });

    const message = useChatStore.getState().chatMessages[sessionId]?.[0];
    expect(message?.status).toBe('cancelled');
    expect(message?.content).toBe('partial');
    expect(message?.processes?.[0]?.status).toBe('cancelled');
  });

  it('preserves a durable partial answer as recovering after stream interruption', async () => {
    chatWithBackendMock.mockImplementation(async (options: StreamingCallbacks) => {
      options.onRunView?.(runningView);
      options.onMessageChunk?.('partial');
      options.onError?.('provider details must not be appended');
    });
    const sessionId = 'session-recovering';
    const messageId = 'message-recovering';
    useChatStore.getState().setSessionMessages(sessionId, [{
      id: messageId,
      role: 'assistant',
      content: '',
      createdAt: new Date(),
    }]);

    const { result } = renderHook(() => useChatStreaming({
      selectedProvider: 'deepseek',
      selectedModel: 'model',
      onConnectionStatusChange: vi.fn(),
    }));

    await act(async () => {
      await result.current.startStreaming({
        messages: [],
        temperature: 0.7,
        activeSessionId: sessionId,
        aiMessageId: messageId,
      });
    });

    const message = useChatStore.getState().chatMessages[sessionId]?.[0];
    expect(message?.status).toBe('recovering');
    expect(message?.content).toBe('partial');
    expect(message?.content).not.toContain('provider details');
    expect(message?.run).toMatchObject({
      phase: 'recovering',
      terminalStatus: null,
      connectionStatus: 'disconnected',
      errorCode: 'stream_interrupted',
    });
  });

  it('keeps a durable run recoverable when completion lacks a terminal status', async () => {
    chatWithBackendMock.mockImplementation(async (options: StreamingCallbacks) => {
      options.onRunView?.(runningView);
      options.onMessageChunk?.('partial');
      options.onComplete?.({ hasDurableRun: true, terminalStatus: null });
    });
    const sessionId = 'session-missing-terminal';
    const messageId = 'message-missing-terminal';
    useChatStore.getState().setSessionMessages(sessionId, [{
      id: messageId,
      role: 'assistant',
      content: '',
      createdAt: new Date(),
    }]);

    const { result } = renderHook(() => useChatStreaming({
      selectedProvider: 'deepseek',
      selectedModel: 'model',
      onConnectionStatusChange: vi.fn(),
    }));

    await act(async () => {
      await result.current.startStreaming({
        messages: [],
        temperature: 0.7,
        activeSessionId: sessionId,
        aiMessageId: messageId,
      });
    });

    const message = useChatStore.getState().chatMessages[sessionId]?.[0];
    expect(message?.status).toBe('recovering');
    expect(message?.content).toBe('partial');
    expect(message?.run).toMatchObject({
      phase: 'recovering',
      terminalStatus: null,
      errorCode: 'missing_terminal_event',
    });
  });

  it('does not call the durable cancel endpoint for a non-durable run', async () => {
    let resolveStream!: () => void;
    chatWithBackendMock.mockImplementation((options: StreamingCallbacks) => {
      options.onRunView?.({ ...runningView, durable: false });
      return new Promise<void>((resolve) => { resolveStream = resolve; });
    });
    const sessionId = 'session-ephemeral';
    const messageId = 'message-ephemeral';
    useChatStore.getState().setSessionMessages(sessionId, [{
      id: messageId,
      role: 'assistant',
      content: '',
      createdAt: new Date(),
    }]);

    const { result } = renderHook(() => useChatStreaming({
      selectedProvider: 'deepseek',
      selectedModel: 'model',
      onConnectionStatusChange: vi.fn(),
    }));

    act(() => {
      void result.current.startStreaming({
        messages: [],
        temperature: 0.7,
        activeSessionId: sessionId,
        aiMessageId: messageId,
      });
    });
    await act(async () => {
      await Promise.resolve();
      result.current.stopGeneration();
      resolveStream();
      await Promise.resolve();
    });

    expect(cancelRunMock).not.toHaveBeenCalled();
    expect(useChatStore.getState().chatMessages[sessionId]?.[0]?.status).toBe('failed');
  });

  it('marks client configuration failures explicitly instead of as stream errors', async () => {
    chatWithBackendMock.mockRejectedValue(new Error('请先在设置中填写 openai 的 API Key'));
    const sessionId = 'session-config-error';
    const messageId = 'message-config-error';
    useChatStore.getState().setSessionMessages(sessionId, [{
      id: messageId,
      role: 'assistant',
      content: '',
      createdAt: new Date(),
    }]);

    const { result } = renderHook(() => useChatStreaming({
      selectedProvider: 'openai',
      selectedModel: 'gpt-3.5-turbo',
      onConnectionStatusChange: vi.fn(),
    }));

    await act(async () => {
      await result.current.startStreaming({
        messages: [],
        temperature: 0.7,
        activeSessionId: sessionId,
        aiMessageId: messageId,
      });
    });

    expect(useChatStore.getState().chatMessages[sessionId]?.[0]?.run).toMatchObject({
      phase: 'failed',
      errorCode: 'configuration_error',
    });
  });
});
