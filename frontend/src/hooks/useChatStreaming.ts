/* eslint-disable @typescript-eslint/no-explicit-any -- streaming event payloads are provider-defined. */
import { useState, useRef, useCallback } from 'react';
import { cancelRun, chatWithBackend } from '@/lib/fetcher';
import {
  KeyedTextRevealQueue,
  TextRevealBuffer,
  revealCharactersPerFrame,
  type RevealField,
} from '@/lib/textRevealBuffer';
import { createRafBatcher } from '@/lib/rafBatcher';
import { selectPendingTool } from '@/lib/processDisplayState';
import useChatStore, { ProcessNode, MessageStatus, RunView } from '@/stores/useChatStore';

const TOOL_REASONS: Record<string, string> = {
  search_anime_advanced: '根据用户查询搜索匹配的动画作品',
  get_anime_info: '获取动画详细信息（评分、简介等）',
  fetch_audience_reviews: '获取观众口碑评价分析',
  get_anime_staff: '查询动画制作人员阵容',
  get_anime_cast: '查询声优配音阵容',
  get_current_time: '获取当前日期时间信息',
  generate_user_profile_tool: '基于对话生成用户偏好画像',
};

const TOOL_LABELS: Record<string, string> = {
  search_anime_advanced: '搜索动画',
  get_anime_info: '动画详情',
  fetch_audience_reviews: '口碑分析',
  get_anime_staff: '制作人员',
  get_anime_cast: '声优阵容',
  get_current_time: '查询时间',
  generate_user_profile_tool: '生成画像',
};

interface PromptConfig {
  persona: string;
  tone: string;
  rules: string;
}

interface StreamingParams {
  messages: any[];
  temperature: number;
  promptConfig?: PromptConfig;
  activeSessionId: string;
  aiMessageId: string;
  resumeRun?: RunView;
  initialContent?: string;
  initialProcesses?: ProcessNode[];
  initialPlan?: string;
}

interface UseChatStreamingOptions {
  selectedProvider: string;
  selectedModel: string;
  onConnectionStatusChange: (status: 'connected' | 'connecting' | 'disconnected') => void;
}

export interface StreamingPreview {
  messageId: string;
  content: string;
  processes: ProcessNode[];
  plan?: string;
  status: MessageStatus;
  run?: RunView;
}

const initialRunView = (): RunView => ({
  runId: null,
  lastSequence: 0,
  durable: null,
  phase: 'thinking',
  terminalStatus: null,
  connectionStatus: 'connecting',
  cancelling: false,
});

function processStatusForTerminal(status: string | null): ProcessNode['status'] {
  switch (status) {
    case 'succeeded': return 'success';
    case 'cancelled': return 'cancelled';
    case 'timeout': return 'timeout';
    default: return 'error';
  }
}

function messageStatusForTerminal(status: string | null): MessageStatus {
  switch (status) {
    case 'succeeded': return 'completed';
    case 'cancelled': return 'cancelled';
    case 'timeout': return 'timeout';
    default: return 'failed';
  }
}

const PROCESS_DISPLAY_LIMIT = 4000;

function formatProcessPayload(value: unknown) {
  if (value == null) return '';
  const text = typeof value === 'string'
    ? value
    : (() => {
        try {
          return JSON.stringify(value, null, 2) ?? String(value);
        } catch {
          return '[unsafe tool data]';
        }
      })();
  return text.length <= PROCESS_DISPLAY_LIMIT
    ? text
    : `${text.slice(0, PROCESS_DISPLAY_LIMIT)}\u2026`;
}

function normalizeProcessStatus(status?: string, errorCode?: string | null): ProcessNode['status'] {
  const marker = String(status || '').trim().toLowerCase();
  const errorMarker = String(errorCode || '').trim().toLowerCase();
  if (marker === 'timeout' || marker === 'timed_out' || errorMarker === 'timeout') return 'timeout';
  if (marker === 'denied' || marker === 'forbidden') return 'denied';
  if (marker === 'cancelled' || marker === 'canceled') return 'cancelled';
  if (marker === 'succeeded' || marker === 'success' || marker === 'completed') return 'success';
  return 'error';
}

function clientErrorCode(error: unknown): string {
  const message = error instanceof Error ? error.message : String(error);
  return message.startsWith('请先在设置中填写 ')
    ? 'configuration_error'
    : 'stream_error';
}

export function useChatStreaming({
  selectedProvider,
  selectedModel,
  onConnectionStatusChange,
}: UseChatStreamingOptions) {
  const [loading, setLoading] = useState(false);
  const [streamingMessageId, setStreamingMessageId] = useState<string | null>(null);
  const [streamingPreview, setStreamingPreview] = useState<StreamingPreview | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const accumulatedContentRef = useRef<string>('');
  const processesRef = useRef<ProcessNode[]>([]);
  const stepCounterRef = useRef<number>(0);
  const planRef = useRef<string>('');
  const pendingContentRef = useRef<string>('');
  const pendingProcessesRef = useRef<ProcessNode[] | null>(null);
  const contentBufferRef = useRef(new TextRevealBuffer());
  const processRevealQueueRef = useRef(new KeyedTextRevealQueue());
  const revealRafIdRef = useRef<number | null>(null);
  const processRevealRafIdRef = useRef<number | null>(null);
  const processCompletionsRef = useRef(new Map<string, Partial<ProcessNode>>());
  const networkCompleteRef = useRef(false);
  const completionStatusRef = useRef<MessageStatus>('completed');
  const terminalStatusRef = useRef<string | null>(null);
  const runViewRef = useRef<RunView>(initialRunView());
  const streamTargetRef = useRef<{ sessionId: string; messageId: string } | null>(null);
  const runIdRef = useRef(0);
  const terminalRef = useRef(false);
  const streamUpdateBatcherRef = useRef(createRafBatcher());

  const { updateMessage } = useChatStore.getState();

  const flushUpdates = useCallback((messageId: string) => {
    const content = pendingContentRef.current;
    const processes = pendingProcessesRef.current;
    const plan = planRef.current;
    const hasProcesses = processes && processes.length > 0;
    const status: MessageStatus = content
      ? 'generating'
      : hasProcesses
        ? 'thinking'
        : 'thinking';
    setStreamingPreview({
      messageId,
      content,
      processes: processes ?? processesRef.current,
      plan: plan || undefined,
      status,
      run: runViewRef.current,
    });
  }, []);

  const scheduleUpdate = useCallback((sessionId: string, messageId: string) => {
    streamUpdateBatcherRef.current(() => flushUpdates(messageId));
  }, [flushUpdates]);

  const updateNow = useCallback((sessionId: string, messageId: string) => {
    scheduleUpdate(sessionId, messageId);
  }, [scheduleUpdate]);

  const finalizeDisplay = useCallback((sessionId: string, messageId: string) => {
    if (contentBufferRef.current.hasPending() || processRevealQueueRef.current.hasPending()) return;

    flushUpdates(messageId);
    updateMessage(
      sessionId,
      accumulatedContentRef.current,
      messageId,
      processesRef.current,
      planRef.current || undefined,
      completionStatusRef.current,
      runViewRef.current,
    );
    setStreamingPreview(null);
    networkCompleteRef.current = false;
    streamTargetRef.current = null;
    setLoading(false);
    setStreamingMessageId(null);
    setCancelling(false);
  }, [flushUpdates, updateMessage]);

  const publishRunView = useCallback((view: RunView) => {
    runViewRef.current = view;
    setCancelling(Boolean(view.cancelling));
    setStreamingPreview((preview) => preview ? { ...preview, run: view } : preview);
    const target = streamTargetRef.current;
    if (target) {
      updateMessage(
        target.sessionId,
        accumulatedContentRef.current,
        target.messageId,
        processesRef.current,
        planRef.current || undefined,
        undefined,
        view,
      );
    }
  }, [updateMessage]);

  const scheduleContentReveal = useCallback((sessionId: string, messageId: string) => {
    if (revealRafIdRef.current !== null) return;

    const revealFrame = () => {
      revealRafIdRef.current = null;
      const backlog = contentBufferRef.current.length;
      const charactersPerFrame = revealCharactersPerFrame(backlog);
      const revealed = contentBufferRef.current.take(charactersPerFrame);

      if (revealed) {
        accumulatedContentRef.current += revealed;
        pendingContentRef.current = accumulatedContentRef.current;
        flushUpdates(messageId);
      }

      if (contentBufferRef.current.hasPending()) {
        revealRafIdRef.current = requestAnimationFrame(revealFrame);
      } else if (networkCompleteRef.current) {
        finalizeDisplay(sessionId, messageId);
      }
    };

    revealRafIdRef.current = requestAnimationFrame(revealFrame);
  }, [finalizeDisplay, flushUpdates]);

  const resetInternal = useCallback(() => {
    processesRef.current = [];
    stepCounterRef.current = 0;
    planRef.current = '';
    accumulatedContentRef.current = '';
    pendingContentRef.current = '';
    pendingProcessesRef.current = null;
    setStreamingPreview(null);
    streamUpdateBatcherRef.current.cancel();
    contentBufferRef.current.clear();
    processRevealQueueRef.current.clear();
    processCompletionsRef.current.clear();
    networkCompleteRef.current = false;
    completionStatusRef.current = 'completed';
    terminalStatusRef.current = null;
    runViewRef.current = initialRunView();
    setCancelling(false);
    if (revealRafIdRef.current !== null) {
      cancelAnimationFrame(revealRafIdRef.current);
      revealRafIdRef.current = null;
    }
    if (processRevealRafIdRef.current !== null) {
      cancelAnimationFrame(processRevealRafIdRef.current);
      processRevealRafIdRef.current = null;
    }
  }, []);

  const addProcessNode = useCallback((node: ProcessNode) => {
    processesRef.current = [...processesRef.current, node];
    pendingProcessesRef.current = processesRef.current;
  }, []);

  const updateProcessNode = useCallback((id: string, updates: Partial<ProcessNode>) => {
    const index = processesRef.current.findIndex((node) => node.id === id);
    if (index === -1) return false;

    const updated = [...processesRef.current];
    updated[index] = { ...updated[index], ...updates };
    processesRef.current = updated;
    pendingProcessesRef.current = updated;
    return true;
  }, []);

  const applyReadyProcessCompletions = useCallback(() => {
    let changed = false;
    for (const [nodeId, completion] of processCompletionsRef.current) {
      if (processRevealQueueRef.current.hasPending(nodeId)) continue;
      changed = updateProcessNode(nodeId, completion) || changed;
      processCompletionsRef.current.delete(nodeId);
    }
    return changed;
  }, [updateProcessNode]);

  const scheduleProcessReveal = useCallback((sessionId: string, messageId: string) => {
    if (processRevealRafIdRef.current !== null) return;

    const revealFrame = () => {
      processRevealRafIdRef.current = null;
      const updates = processRevealQueueRef.current.takeFrame();

      for (const update of updates) {
        const node = processesRef.current.find((item) => item.id === update.nodeId);
        if (!node) continue;
        const fieldValue = node[update.field];
        const previous = typeof fieldValue === 'string' ? fieldValue : '';
        updateProcessNode(update.nodeId, {
          [update.field]: previous + update.text,
        });
      }

      const completionChanged = applyReadyProcessCompletions();
      if (updates.length > 0 || completionChanged) {
        flushUpdates(messageId);
      }

      if (processRevealQueueRef.current.hasPending()) {
        processRevealRafIdRef.current = requestAnimationFrame(revealFrame);
      } else if (networkCompleteRef.current) {
        finalizeDisplay(sessionId, messageId);
      }
    };

    processRevealRafIdRef.current = requestAnimationFrame(revealFrame);
  }, [applyReadyProcessCompletions, finalizeDisplay, flushUpdates, updateProcessNode]);

  const enqueueProcessReveal = useCallback((
    sessionId: string,
    messageId: string,
    nodeId: string,
    field: RevealField,
    value: unknown,
  ) => {
    const text = formatProcessPayload(value);
    if (!text) return false;
    processRevealQueueRef.current.append(nodeId, field, text);
    scheduleProcessReveal(sessionId, messageId);
    return true;
  }, [scheduleProcessReveal]);

  const findTool = useCallback((name: string, sourceId?: string, includeTerminal = false) => {
    const tools = processesRef.current.filter((node) => node.type === 'tool_call');
    if (sourceId) {
      const exact = [...tools].reverse().find((tool) => tool.sourceId === sourceId);
      if (exact && (includeTerminal || exact.status === 'pending')) return exact;
    }
    return selectPendingTool(tools, name, sourceId);
  }, []);

  const findPendingThought = useCallback(() => {
    for (let index = processesRef.current.length - 1; index >= 0; index -= 1) {
      const node = processesRef.current[index];
      if (node.type === 'thought' && node.status === 'pending') return node;
    }
    return undefined;
  }, []);

  const stopGeneration = useCallback(() => {
    const target = streamTargetRef.current;
    const runView = runViewRef.current;
    if (target && runView.durable === true && runView.runId && !runView.terminalStatus) {
      const cancellingView: RunView = {
        ...runView,
        cancelling: true,
        connectionStatus: 'connected',
      };
      publishRunView(cancellingView);
      void cancelRun(runView.runId).catch(() => {
        publishRunView({
          ...runViewRef.current,
          cancelling: false,
          errorCode: 'cancel_request_failed',
        });
      });
      return;
    }

    terminalRef.current = true;
    completionStatusRef.current = 'failed';
    contentBufferRef.current.clear();
    processRevealQueueRef.current.clear();
    processCompletionsRef.current.clear();
    if (revealRafIdRef.current !== null) {
      cancelAnimationFrame(revealRafIdRef.current);
      revealRafIdRef.current = null;
    }
    if (processRevealRafIdRef.current !== null) {
      cancelAnimationFrame(processRevealRafIdRef.current);
      processRevealRafIdRef.current = null;
    }
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }
    if (target) {
      const stoppedProcesses = processesRef.current.map((node) =>
        node.status === 'pending' ? { ...node, status: 'error' as const } : node
      );
      processesRef.current = stoppedProcesses;
      pendingProcessesRef.current = stoppedProcesses;
      updateMessage(
        target.sessionId,
        accumulatedContentRef.current,
        target.messageId,
        stoppedProcesses,
        planRef.current || undefined,
        'failed',
        {
          ...runViewRef.current,
          phase: 'failed',
          connectionStatus: 'disconnected',
          errorCode: 'client_stopped',
        },
      );
      setStreamingPreview(null);
    }
    streamTargetRef.current = null;
    setLoading(false);
    setStreamingMessageId(null);
    setCancelling(false);
  }, [publishRunView, updateMessage]);

  const startStreaming = useCallback(async (params: StreamingParams) => {
    const {
      messages,
      temperature,
      promptConfig,
      activeSessionId,
      aiMessageId,
      resumeRun,
      initialContent,
      initialProcesses,
      initialPlan,
    } = params;
    abortRef.current?.abort();
    const runId = runIdRef.current + 1;
    runIdRef.current = runId;
    terminalRef.current = false;
    const isCurrentRun = () => runIdRef.current === runId;
    const acceptsStreamEvent = () => isCurrentRun() && !terminalRef.current;

    setLoading(true);
    setStreamingMessageId(aiMessageId);
    if (resumeRun) {
      runViewRef.current = {
        ...resumeRun,
        connectionStatus: 'connecting',
        cancelling: false,
      };
      processesRef.current = initialProcesses || [];
      pendingProcessesRef.current = processesRef.current;
      accumulatedContentRef.current = initialContent || '';
      pendingContentRef.current = accumulatedContentRef.current;
      planRef.current = initialPlan || '';
      contentBufferRef.current.clear();
      processRevealQueueRef.current.clear();
      processCompletionsRef.current.clear();
      networkCompleteRef.current = false;
      terminalStatusRef.current = resumeRun.terminalStatus;
      setCancelling(false);
    } else {
      resetInternal();
    }
    streamTargetRef.current = { sessionId: activeSessionId, messageId: aiMessageId };

    const abortController = new AbortController();
    abortRef.current = abortController;

    const store = useChatStore.getState();

    try {
      await chatWithBackend({
        messages,
        provider: selectedProvider,
        model: selectedModel,
        temperature,
        prompt_config: promptConfig,
        thread_id: activeSessionId,
        abortSignal: abortController.signal,
        resumeRun: resumeRun?.runId
          ? {
              runId: resumeRun.runId,
              after: resumeRun.lastSequence,
              durable: resumeRun.durable,
              threadId: activeSessionId,
            }
          : undefined,
        onMessageChunk: (chunk) => {
          if (!acceptsStreamEvent()) return;
          accumulatedContentRef.current += chunk;
          pendingContentRef.current = accumulatedContentRef.current;
          updateNow(activeSessionId, aiMessageId);
        },
        onMessageStart: () => {
          if (!acceptsStreamEvent()) return;
          for (const node of processesRef.current) {
            if (node.type === 'thought' && node.status === 'pending') {
              processCompletionsRef.current.set(node.id, { status: 'success' });
            }
          }
          applyReadyProcessCompletions();
          if (processRevealQueueRef.current.hasPending()) {
            scheduleProcessReveal(activeSessionId, aiMessageId);
          }
          updateNow(activeSessionId, aiMessageId);
        },
        onThinkingStart: () => {
          if (!acceptsStreamEvent()) return;
          const lastNode = processesRef.current[processesRef.current.length - 1];
          // The server sends an immediate start event so the UI is responsive.
          // Reuse that empty node when the provider begins to stream reasoning.
          if (lastNode?.type === 'thought' && lastNode.status === 'pending' && !lastNode.details) {
            return;
          }
          stepCounterRef.current += 1;
          addProcessNode({
            id: `thought-${stepCounterRef.current}-${Date.now()}`,
            stepNumber: stepCounterRef.current,
            type: 'thought',
            status: 'pending',
            title: '推理',
          });
          updateNow(activeSessionId, aiMessageId);
        },
        onThinkingChunk: (chunk) => {
          if (!acceptsStreamEvent()) return;
          let thought = findPendingThought();
          if (!thought) {
            stepCounterRef.current += 1;
            thought = {
              id: `thought-${stepCounterRef.current}-${Date.now()}`,
              stepNumber: stepCounterRef.current,
              type: 'thought',
              status: 'pending',
              title: '推理',
            };
            addProcessNode(thought);
          }
          updateProcessNode(thought.id, {
            details: `${thought.details || ''}${chunk}`,
          });
          updateNow(activeSessionId, aiMessageId);
        },
        onThinkingEnd: () => {
          if (!acceptsStreamEvent()) return;
          const thought = findPendingThought();
          if (thought) {
            processCompletionsRef.current.set(thought.id, { status: 'success' });
            applyReadyProcessCompletions();
            if (processRevealQueueRef.current.hasPending(thought.id)) {
              scheduleProcessReveal(activeSessionId, aiMessageId);
            }
          }
          updateNow(activeSessionId, aiMessageId);
        },
        onToolCallDelta: (sourceId, name, delta) => {
          if (!acceptsStreamEvent()) return;
          let tool = findTool(name, sourceId);
          if (!tool) {
            stepCounterRef.current += 1;
            tool = {
              id: `tool-${sourceId || name}-${stepCounterRef.current}-${Date.now()}`,
              sourceId,
              stepNumber: stepCounterRef.current,
              type: 'tool_call',
              status: 'pending',
              title: TOOL_LABELS[name] || name,
              name,
              reason: TOOL_REASONS[name],
            };
            addProcessNode(tool);
          }
          updateProcessNode(tool.id, {
            details: `${tool.details || ''}${delta}`,
          });
          updateNow(activeSessionId, aiMessageId);
        },
        onToolCallStart: (sourceId, name, inputs) => {
          if (!acceptsStreamEvent()) return;
          // Models usually emit argument deltas before the tool runtime emits a
          // start event. Merge that live node instead of showing two calls.
          const existing = findTool(name, sourceId, true);
          if (existing) {
            updateProcessNode(existing.id, {
              title: TOOL_LABELS[name] || name,
              reason: TOOL_REASONS[name],
            });
            if (existing.details == null) {
              updateProcessNode(existing.id, {
                details: formatProcessPayload(inputs),
              });
            }
          } else {
            stepCounterRef.current += 1;
            const tool: ProcessNode = {
              id: `tool-${name}-${stepCounterRef.current}-${Date.now()}`,
              sourceId,
              stepNumber: stepCounterRef.current,
              type: 'tool_call',
              status: 'pending',
              title: TOOL_LABELS[name] || name,
              name,
              reason: TOOL_REASONS[name],
            };
            addProcessNode(tool);
            updateProcessNode(tool.id, {
              details: formatProcessPayload(inputs),
            });
          }
          updateNow(activeSessionId, aiMessageId);
        },
        onToolCallEnd: (sourceId, name, output, durationMs, status, errorCode) => {
          if (!acceptsStreamEvent()) return;
          let tool = findTool(name, sourceId, true);
          if (!tool) {
            stepCounterRef.current += 1;
            tool = {
              id: `tool-${name}-${stepCounterRef.current}-${Date.now()}`,
              sourceId,
              stepNumber: stepCounterRef.current,
              type: 'tool_call',
              status: 'pending',
              title: TOOL_LABELS[name] || name,
              name,
              reason: TOOL_REASONS[name],
            };
            addProcessNode(tool);
          }
          if (tool.status !== 'pending') return;
          const endUpdates: Partial<ProcessNode> = {
            output: formatProcessPayload(output),
            status: normalizeProcessStatus(status, errorCode),
            errorCode: errorCode || undefined,
          };
          if (durationMs != null) endUpdates.duration = durationMs;
          updateProcessNode(tool.id, endUpdates);
          updateNow(activeSessionId, aiMessageId);
        },
        onPlanUpdate: (planText) => {
          if (!acceptsStreamEvent()) return;
          planRef.current = planText;
          updateNow(activeSessionId, aiMessageId);
        },
        onProgress: () => {
        },
        onConnectionStatus: (status) => {
          if (!isCurrentRun()) return;
          onConnectionStatusChange(status);
          publishRunView({ ...runViewRef.current, connectionStatus: status });
        },
        onRunStatus: (status) => {
          if (!acceptsStreamEvent()) return;
          terminalStatusRef.current = status.status;
        },
        onRunView: (view) => {
          if (!acceptsStreamEvent()) return;
          const mergedView = view.terminalStatus
            ? { ...view, cancelling: false }
            : { ...view, cancelling: runViewRef.current.cancelling || view.cancelling };
          terminalStatusRef.current = mergedView.terminalStatus;
          publishRunView(mergedView);
        },
        onError: (_errorMessage, serverErrorCode) => {
          if (!acceptsStreamEvent()) return;
          terminalRef.current = true;
          contentBufferRef.current.clear();
          processRevealQueueRef.current.clear();
          processCompletionsRef.current.clear();
          if (processRevealRafIdRef.current !== null) {
            cancelAnimationFrame(processRevealRafIdRef.current);
            processRevealRafIdRef.current = null;
          }
          const isDurableRun = runViewRef.current.durable === true;
          const processes = isDurableRun
            ? processesRef.current
            : processesRef.current.map(p => ({
              ...p,
              status: p.status === 'pending' ? 'error' as const : p.status,
            }));
          pendingProcessesRef.current = processes;
          processesRef.current = processes;
          pendingContentRef.current = accumulatedContentRef.current;
          completionStatusRef.current = isDurableRun ? 'recovering' : 'failed';
          publishRunView({
            ...runViewRef.current,
            phase: isDurableRun ? 'recovering' : 'failed',
            connectionStatus: 'disconnected',
            errorCode: isDurableRun ? 'stream_interrupted' : (serverErrorCode || 'stream_error'),
            terminalStatus: null,
            cancelling: false,
          });
          networkCompleteRef.current = true;
          finalizeDisplay(activeSessionId, aiMessageId);
        },
        onComplete: (metadata) => {
          if (!isCurrentRun() || terminalRef.current) return;
          const terminalStatus = terminalStatusRef.current;
          if (!terminalStatus) {
            if (!metadata?.hasDurableRun) {
              terminalRef.current = true;
              for (const node of processesRef.current) {
                if (node.status === 'pending') {
                  processCompletionsRef.current.set(node.id, { status: 'success' });
                }
              }
              applyReadyProcessCompletions();
              completionStatusRef.current = 'completed';
              publishRunView({
                ...runViewRef.current,
                phase: 'completed',
                terminalStatus: null,
                cancelling: false,
              });
              networkCompleteRef.current = true;
              finalizeDisplay(activeSessionId, aiMessageId);
              return;
            }
            terminalRef.current = true;
            completionStatusRef.current = 'recovering';
            pendingProcessesRef.current = processesRef.current;
            publishRunView({
              ...runViewRef.current,
              phase: 'recovering',
              connectionStatus: 'disconnected',
              errorCode: 'missing_terminal_event',
              terminalStatus: null,
              cancelling: false,
            });
            networkCompleteRef.current = true;
            finalizeDisplay(activeSessionId, aiMessageId);
            return;
          }
          terminalRef.current = true;
          for (const node of processesRef.current) {
            if (node.status === 'pending' && !processCompletionsRef.current.has(node.id)) {
              processCompletionsRef.current.set(node.id, {
                status: processStatusForTerminal(terminalStatus),
              });
            }
          }
          applyReadyProcessCompletions();
          completionStatusRef.current = messageStatusForTerminal(terminalStatus);
          publishRunView({
            ...runViewRef.current,
            terminalStatus: terminalStatus as RunView['terminalStatus'],
            phase: terminalStatus === 'succeeded'
              ? 'completed'
              : terminalStatus === 'cancelled'
                ? 'cancelled'
                : terminalStatus === 'timeout'
                  ? 'timeout'
                  : 'failed',
            cancelling: false,
          });
          networkCompleteRef.current = true;
          finalizeDisplay(activeSessionId, aiMessageId);
        },
      });
    } catch (error) {
      if (!isCurrentRun()) return;
      terminalRef.current = true;
      contentBufferRef.current.clear();
      processRevealQueueRef.current.clear();
      processCompletionsRef.current.clear();
      if (revealRafIdRef.current !== null) {
        cancelAnimationFrame(revealRafIdRef.current);
        revealRafIdRef.current = null;
      }
      if (processRevealRafIdRef.current !== null) {
        cancelAnimationFrame(processRevealRafIdRef.current);
        processRevealRafIdRef.current = null;
      }
      const isDurableRun = runViewRef.current.durable === true;
      const errorContent = accumulatedContentRef.current;
      pendingContentRef.current = errorContent;
      completionStatusRef.current = isDurableRun ? 'recovering' : 'failed';
      publishRunView({
        ...runViewRef.current,
        phase: isDurableRun ? 'recovering' : 'failed',
        connectionStatus: 'disconnected',
        errorCode: isDurableRun ? 'stream_interrupted' : clientErrorCode(error),
        terminalStatus: null,
        cancelling: false,
      });
      store.updateMessage(
        activeSessionId,
        errorContent,
        aiMessageId,
        processesRef.current,
        planRef.current || undefined,
        completionStatusRef.current,
        runViewRef.current,
      );
      setStreamingPreview(null);
      streamTargetRef.current = null;
      setLoading(false);
      setStreamingMessageId(null);
    } finally {
      if (abortRef.current === abortController) abortRef.current = null;
    }
  }, [selectedProvider, selectedModel, resetInternal, addProcessNode, findPendingThought, findTool, applyReadyProcessCompletions, updateProcessNode, updateNow, finalizeDisplay, onConnectionStatusChange, scheduleProcessReveal, publishRunView]);

  const resumeRun = useCallback(async ({
    sessionId,
    messageId,
    run,
    content = '',
    processes = [],
    plan = '',
  }: { sessionId: string; messageId: string; run: RunView; content?: string; processes?: ProcessNode[]; plan?: string }) => {
    await startStreaming({
      messages: [],
      temperature: 0.7,
      activeSessionId: sessionId,
      aiMessageId: messageId,
      resumeRun: run,
      initialContent: content,
      initialProcesses: processes,
      initialPlan: plan,
    });
  }, [startStreaming]);

  return { loading, cancelling, streamingMessageId, streamingPreview, startStreaming, resumeRun, stopGeneration };
}
