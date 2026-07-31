/* eslint-disable @typescript-eslint/no-explicit-any -- streaming event payloads are provider-defined. */
import { useState, useRef, useCallback } from 'react';
import { chatWithBackend } from '@/lib/fetcher';
import {
  KeyedTextRevealQueue,
  TextRevealBuffer,
  revealCharactersPerFrame,
  type RevealField,
} from '@/lib/textRevealBuffer';
import { createRafBatcher } from '@/lib/rafBatcher';
import { selectPendingTool } from '@/lib/processDisplayState';
import useChatStore, { ProcessNode, MessageStatus } from '@/stores/useChatStore';

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
}

function formatProcessPayload(value: unknown) {
  if (value == null) return '';
  if (typeof value === 'string') return value;
  try {
    return JSON.stringify(value, null, 2) ?? String(value);
  } catch {
    return String(value);
  }
}

export function useChatStreaming({
  selectedProvider,
  selectedModel,
  onConnectionStatusChange,
}: UseChatStreamingOptions) {
  const [loading, setLoading] = useState(false);
  const [streamingMessageId, setStreamingMessageId] = useState<string | null>(null);
  const [streamingPreview, setStreamingPreview] = useState<StreamingPreview | null>(null);
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
    );
    setStreamingPreview(null);
    networkCompleteRef.current = false;
    streamTargetRef.current = null;
    setLoading(false);
    setStreamingMessageId(null);
  }, [flushUpdates, updateMessage]);

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

  const findPendingTool = useCallback((name: string, sourceId?: string) => {
    return selectPendingTool(
      processesRef.current.filter((node) => node.type === 'tool_call'),
      name,
      sourceId,
    );
  }, []);

  const findPendingThought = useCallback(() => {
    for (let index = processesRef.current.length - 1; index >= 0; index -= 1) {
      const node = processesRef.current[index];
      if (node.type === 'thought' && node.status === 'pending') return node;
    }
    return undefined;
  }, []);

  const stopGeneration = useCallback(() => {
    terminalRef.current = true;
    completionStatusRef.current = 'error';
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
    const target = streamTargetRef.current;
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
        'error',
      );
      setStreamingPreview(null);
    }
    streamTargetRef.current = null;
    setLoading(false);
    setStreamingMessageId(null);
  }, [updateMessage]);

  const startStreaming = useCallback(async (params: StreamingParams) => {
    const { messages, temperature, promptConfig, activeSessionId, aiMessageId } = params;
    abortRef.current?.abort();
    const runId = runIdRef.current + 1;
    runIdRef.current = runId;
    terminalRef.current = false;
    const isCurrentRun = () => runIdRef.current === runId;
    const acceptsStreamEvent = () => isCurrentRun() && !terminalRef.current;

    setLoading(true);
    setStreamingMessageId(aiMessageId);
    resetInternal();
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
          let tool = findPendingTool(name, sourceId);
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
          const existing = findPendingTool(name, sourceId) || findPendingTool(name);
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
            tool.details = formatProcessPayload(inputs);
          }
          updateNow(activeSessionId, aiMessageId);
        },
        onToolCallEnd: (sourceId, name, output, durationMs, status) => {
          if (!acceptsStreamEvent()) return;
          let tool = findPendingTool(name, sourceId) || findPendingTool(name);
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
          updateProcessNode(tool.id, {
            output: formatProcessPayload(output),
            status: (status || 'success') as ProcessNode['status'],
            duration: durationMs || 0,
          });
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
          if (isCurrentRun()) onConnectionStatusChange(status);
        },
        onRunStatus: (status) => {
          if (!isCurrentRun()) return;
          terminalStatusRef.current = status.status;
        },
        onError: (error) => {
          if (!acceptsStreamEvent()) return;
          terminalRef.current = true;
          contentBufferRef.current.clear();
          processRevealQueueRef.current.clear();
          processCompletionsRef.current.clear();
          if (processRevealRafIdRef.current !== null) {
            cancelAnimationFrame(processRevealRafIdRef.current);
            processRevealRafIdRef.current = null;
          }
          const processes = processesRef.current.map(p => ({
            ...p,
            status: p.status === 'pending' ? 'error' as const : p.status,
          }));
          pendingProcessesRef.current = processes;
          processesRef.current = processes;
          accumulatedContentRef.current = `Error: ${error}`;
          pendingContentRef.current = accumulatedContentRef.current;
          completionStatusRef.current = 'error';
          networkCompleteRef.current = true;
          finalizeDisplay(activeSessionId, aiMessageId);
        },
        onComplete: (metadata) => {
          if (!acceptsStreamEvent()) return;
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
              networkCompleteRef.current = true;
              finalizeDisplay(activeSessionId, aiMessageId);
              return;
            }
            terminalRef.current = true;
            completionStatusRef.current = 'error';
            for (const node of processesRef.current) {
              if (node.status === 'pending') {
                processCompletionsRef.current.set(node.id, { status: 'error' });
              }
            }
            applyReadyProcessCompletions();
            networkCompleteRef.current = true;
            finalizeDisplay(activeSessionId, aiMessageId);
            return;
          }
          terminalRef.current = true;
          for (const node of processesRef.current) {
            if (node.status === 'pending' && !processCompletionsRef.current.has(node.id)) {
              processCompletionsRef.current.set(node.id, {
                status: terminalStatus === 'succeeded' ? 'success' : 'error',
              });
            }
          }
          applyReadyProcessCompletions();
          completionStatusRef.current = terminalStatus === 'succeeded' ? 'completed' : 'error';
          networkCompleteRef.current = true;
          finalizeDisplay(activeSessionId, aiMessageId);
        },
      });
    } catch (error) {
      if (!isCurrentRun()) return;
      terminalRef.current = true;
      console.error('Error streaming:', error);
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
      const errorContent = `Error: ${error instanceof Error ? error.message : 'Unknown error'}`;
      accumulatedContentRef.current = errorContent;
      pendingContentRef.current = errorContent;
      store.updateMessage(
        activeSessionId,
        errorContent,
        aiMessageId,
        processesRef.current,
        planRef.current || undefined,
        'error',
      );
      setStreamingPreview(null);
      streamTargetRef.current = null;
      setLoading(false);
      setStreamingMessageId(null);
    } finally {
      if (abortRef.current === abortController) abortRef.current = null;
    }
  }, [selectedProvider, selectedModel, resetInternal, addProcessNode, findPendingThought, findPendingTool, applyReadyProcessCompletions, updateProcessNode, updateNow, finalizeDisplay, onConnectionStatusChange, scheduleProcessReveal]);

  return { loading, streamingMessageId, streamingPreview, startStreaming, stopGeneration };
}
