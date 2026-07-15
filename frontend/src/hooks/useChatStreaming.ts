import { useState, useRef, useCallback } from 'react';
import { chatWithBackend } from '@/lib/fetcher';
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

export function useChatStreaming({
  selectedProvider,
  selectedModel,
  onConnectionStatusChange,
}: UseChatStreamingOptions) {
  const [loading, setLoading] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const accumulatedContentRef = useRef<string>('');
  const processesRef = useRef<ProcessNode[]>([]);
  const stepCounterRef = useRef<number>(0);
  const planRef = useRef<string>('');
  const rafIdRef = useRef<number | null>(null);
  const pendingContentRef = useRef<string>('');
  const pendingProcessesRef = useRef<ProcessNode[] | null>(null);

  const { updateMessage } = useChatStore.getState();

  const flushUpdates = useCallback((sessionId: string, messageId: string) => {
    if (rafIdRef.current !== null) {
      cancelAnimationFrame(rafIdRef.current);
      rafIdRef.current = null;
    }
    const content = pendingContentRef.current;
    const processes = pendingProcessesRef.current;
    const plan = planRef.current;
    const hasProcesses = processes && processes.length > 0;
    const status: MessageStatus = content
      ? 'generating'
      : hasProcesses
        ? 'thinking'
        : 'thinking';
    updateMessage(sessionId, content, messageId, processes ?? undefined, plan || undefined, status);
  }, [updateMessage]);

  const scheduleUpdate = useCallback((sessionId: string, messageId: string) => {
    if (rafIdRef.current !== null) return;
    rafIdRef.current = requestAnimationFrame(() => {
      rafIdRef.current = null;
      flushUpdates(sessionId, messageId);
    });
  }, [flushUpdates]);

  const updateNow = useCallback((sessionId: string, messageId: string) => {
    flushUpdates(sessionId, messageId);
  }, [flushUpdates]);

  const resetInternal = useCallback(() => {
    processesRef.current = [];
    stepCounterRef.current = 0;
    planRef.current = '';
    accumulatedContentRef.current = '';
    pendingContentRef.current = '';
    pendingProcessesRef.current = null;
    if (rafIdRef.current !== null) {
      cancelAnimationFrame(rafIdRef.current);
      rafIdRef.current = null;
    }
  }, []);

  const addProcessNode = useCallback((node: ProcessNode) => {
    processesRef.current = [...processesRef.current, node];
    pendingProcessesRef.current = processesRef.current;
  }, []);

  const updateLastProcessNode = useCallback((updates: Partial<ProcessNode>) => {
    if (processesRef.current.length === 0) return;
    const updated = [...processesRef.current];
    updated[updated.length - 1] = { ...updated[updated.length - 1], ...updates };
    processesRef.current = updated;
    pendingProcessesRef.current = processesRef.current;
  }, []);

  const stopGeneration = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }
    setLoading(false);
  }, []);

  const startStreaming = useCallback(async (params: StreamingParams) => {
    const { messages, temperature, promptConfig, activeSessionId, aiMessageId } = params;

    setLoading(true);
    resetInternal();

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
          accumulatedContentRef.current += chunk;
          pendingContentRef.current = accumulatedContentRef.current;
          scheduleUpdate(activeSessionId, aiMessageId);
        },
        onMessageStart: () => {
          processesRef.current = processesRef.current.map(p =>
            p.type === 'thought' && p.status === 'pending'
              ? { ...p, status: 'success' as const }
              : p
          );
          pendingProcessesRef.current = processesRef.current;
        },
        onThinkingStart: () => {
          stepCounterRef.current += 1;
          addProcessNode({
            id: `thought-${Date.now()}`,
            stepNumber: stepCounterRef.current,
            type: 'thought',
            status: 'pending',
            title: '推理',
          });
          updateNow(activeSessionId, aiMessageId);
        },
        onThinkingChunk: (chunk) => {
          const current = processesRef.current;
          if (current.length > 0 && current[current.length - 1].type === 'thought') {
            const prev = current[current.length - 1].details || '';
            updateLastProcessNode({ details: prev + chunk });
          } else {
            stepCounterRef.current += 1;
            addProcessNode({
              id: `thought-${Date.now()}`,
              stepNumber: stepCounterRef.current,
              type: 'thought',
              status: 'pending',
              title: '推理',
              details: chunk,
            });
          }
          scheduleUpdate(activeSessionId, aiMessageId);
        },
        onThinkingEnd: () => {
          updateLastProcessNode({ status: 'success' });
          updateNow(activeSessionId, aiMessageId);
        },
        onToolCallDelta: (_id, name, delta) => {
          const current = processesRef.current;
          const lastIdx = current.length - 1;
          if (lastIdx >= 0 && current[lastIdx].type === 'tool_call' && current[lastIdx].status === 'pending') {
            const prev = current[lastIdx].details || '';
            updateLastProcessNode({ details: prev + delta });
          } else {
            stepCounterRef.current += 1;
            addProcessNode({
              id: `tool-${name}-${Date.now()}`,
              stepNumber: stepCounterRef.current,
              type: 'tool_call',
              status: 'pending',
              title: TOOL_LABELS[name] || name,
              name,
              reason: TOOL_REASONS[name],
              details: delta,
            });
          }
          scheduleUpdate(activeSessionId, aiMessageId);
        },
        onToolCallStart: (name, inputs) => {
          stepCounterRef.current += 1;
          addProcessNode({
            id: `tool-${name}-${Date.now()}`,
            stepNumber: stepCounterRef.current,
            type: 'tool_call',
            status: 'pending',
            title: TOOL_LABELS[name] || name,
            name,
            reason: TOOL_REASONS[name],
            details: inputs,
          });
          updateNow(activeSessionId, aiMessageId);
        },
        onToolCallEnd: (name, output, durationMs, status) => {
          updateLastProcessNode({
            status: (status || 'success') as ProcessNode['status'],
            output,
            duration: durationMs || 0,
          });
          updateNow(activeSessionId, aiMessageId);
        },
        onPlanUpdate: (planText) => {
          planRef.current = planText;
        },
        onProgress: () => {
        },
        onConnectionStatus: onConnectionStatusChange,
        onError: (error) => {
          const processes = processesRef.current.map(p => ({
            ...p,
            status: p.status === 'pending' ? 'error' as const : p.status,
          }));
          pendingProcessesRef.current = processes;
          processesRef.current = processes;
          accumulatedContentRef.current = `Error: ${error}`;
          pendingContentRef.current = accumulatedContentRef.current;
          updateNow(activeSessionId, aiMessageId);
        },
        onComplete: () => {
          updateNow(activeSessionId, aiMessageId);
          setLoading(false);
        },
      });
    } catch (error) {
      console.error('Error streaming:', error);
      store.updateMessage(activeSessionId, `Error: ${error instanceof Error ? error.message : 'Unknown error'}`);
    } finally {
      if (rafIdRef.current !== null) {
        cancelAnimationFrame(rafIdRef.current);
        rafIdRef.current = null;
      }
      setLoading(false);
    }
  }, [selectedProvider, selectedModel, resetInternal, addProcessNode, updateLastProcessNode, scheduleUpdate, updateNow, onConnectionStatusChange]);

  return { loading, startStreaming, stopGeneration };
}
