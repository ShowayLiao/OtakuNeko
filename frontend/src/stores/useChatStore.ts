import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { v4 as uuidv4 } from 'uuid';

export type ProcessNodeType = 'thought' | 'tool_call';
export type ProcessNodeStatus = 'pending' | 'success' | 'error' | 'denied' | 'cancelled' | 'timeout';

export type RunPhase = 'thinking' | 'executing' | 'responding' | 'recovering' | 'completed' | 'failed' | 'cancelled' | 'timeout';
export type RunTerminalStatus = 'succeeded' | 'failed' | 'cancelled' | 'timeout';

export interface RunView {
  runId: string | null;
  lastSequence: number;
  durable: boolean | null;
  phase: RunPhase;
  terminalStatus: RunTerminalStatus | null;
  errorCode?: string | null;
  connectionStatus?: 'connected' | 'connecting' | 'disconnected';
  cancelling?: boolean;
}

export interface ProcessNode {
  id: string;
  /** Provider tool-call id when it is available. Used to merge streamed argument deltas. */
  sourceId?: string;
  stepNumber: number;
  type: ProcessNodeType;
  status: ProcessNodeStatus;
  title: string;
  duration?: number;
  details?: unknown;
  output?: unknown;
  errorCode?: string;
  name?: string;
  reason?: string;
}

export interface ToolCall {
  id: string;
  name: string;
  inputs?: unknown;
  status: 'running' | 'success' | 'error';
  output?: unknown;
  durationMs?: number;
  reason?: string;
}

export interface ProgressStep {
  name: string;
  done: boolean;
  durationMs: number;
}

export type MessageStatus = 'thinking' | 'generating' | 'recovering' | 'completed' | 'failed' | 'cancelled' | 'timeout' | 'error';

export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  createdAt: Date;
  extra?: Record<string, unknown>;
  processes?: ProcessNode[];
  status?: MessageStatus;
  plan?: string;
  run?: RunView;
}

export interface Session {
  id: string;
  title: string;
  updatedAt: Date;
}

export interface SessionConfig {
  model: string;
  provider: string;
  role: string;
}

interface ChatStore {
  sessions: Session[];
  chatMessages: Record<string, Message[]>;
  sessionConfigs: Record<string, SessionConfig>;
  activeSessionId: string | null;

  createSession: () => string;
  sendMessage: (sessionId: string, content: string | Message) => void;
  updateMessage: (sessionId: string, content: string, messageId?: string, processes?: ProcessNode[], plan?: string, status?: MessageStatus, run?: RunView) => void;
  switchSession: (sessionId: string) => void;
  deleteSession: (sessionId: string) => void;
  updateSessionTitle: (sessionId: string, title: string) => void;
  setSessionMessages: (sessionId: string, messages: Message[]) => void;
  setSessionConfig: (sessionId: string, config: Partial<SessionConfig>) => void;
}

const useChatStore = create<ChatStore>()(
  persist(
    (set, get) => ({
      sessions: [],
      chatMessages: {},
      sessionConfigs: {},
      activeSessionId: null,

      createSession: () => {
        const sessionId = uuidv4();
        const newSession: Session = {
          id: sessionId,
          title: '新会话',
          updatedAt: new Date(),
        };

        set((state) => ({
          sessions: [...state.sessions, newSession],
          chatMessages: { ...state.chatMessages, [sessionId]: [] },
          activeSessionId: sessionId,
        }));

        return sessionId;
      },

      sendMessage: (sessionId, content, extra?: Record<string, unknown>) => {
        set((state) => {
          const currentMessages = state.chatMessages[sessionId] || [];
          let message: Message;
          if (typeof content === 'string') {
            message = {
              id: uuidv4(),
              role: 'user',
              content,
              createdAt: new Date(),
              extra,
            };
          } else {
            message = content;
          }

          const updatedSessions = state.sessions.map((session) =>
            session.id === sessionId
              ? { ...session, updatedAt: new Date() }
              : session
          );

          return {
            chatMessages: { ...state.chatMessages, [sessionId]: [...currentMessages, message] },
            sessions: updatedSessions,
          };
        });
      },

      updateMessage: (sessionId: string, content: string, messageId?: string, processes?: ProcessNode[], plan?: string, status?: MessageStatus, run?: RunView) => {
        set((state) => {
          const currentMessages = state.chatMessages[sessionId] || [];
          const updatedMessages = [...currentMessages];

          const applyUpdates = (msg: Message): Message => {
            const result = { ...msg, content };
            if (processes !== undefined) result.processes = processes;
            if (plan !== undefined) result.plan = plan;
            if (status !== undefined) result.status = status;
            if (run !== undefined) result.run = run;
            return result;
          };

          if (messageId) {
            const messageIndex = updatedMessages.findIndex(msg => msg.id === messageId);
            if (messageIndex !== -1) {
              updatedMessages[messageIndex] = applyUpdates(updatedMessages[messageIndex]);
            } else {
              const assistantMessage: Message = applyUpdates({
                id: uuidv4(),
                role: 'assistant',
                content: content || '',
                createdAt: new Date(),
              });
              updatedMessages.push(assistantMessage);
            }
          } else {
            const lastMessage = updatedMessages[updatedMessages.length - 1];
            if (!lastMessage || lastMessage.role !== 'assistant') {
              const assistantMessage: Message = applyUpdates({
                id: uuidv4(),
                role: 'assistant',
                content: content || '',
                createdAt: new Date(),
              });
              updatedMessages.push(assistantMessage);
            } else {
              updatedMessages[updatedMessages.length - 1] = applyUpdates(lastMessage);
            }
          }

          const updatedSessions = state.sessions.map((session) =>
            session.id === sessionId
              ? { ...session, updatedAt: new Date() }
              : session
          );

          return {
            chatMessages: { ...state.chatMessages, [sessionId]: updatedMessages },
            sessions: updatedSessions,
          };
        });
      },

      switchSession: (sessionId) => {
        set(() => ({
          activeSessionId: sessionId,
        }));
      },

      deleteSession: (sessionId) => {
        set((state) => {
          const updatedSessions = state.sessions.filter(
            (session) => session.id !== sessionId
          );
          const { [sessionId]: _, ...restMessages } = state.chatMessages;
          const { [sessionId]: __, ...restConfigs } = state.sessionConfigs;

          let newActiveSessionId = state.activeSessionId;
          if (state.activeSessionId === sessionId) {
            newActiveSessionId = updatedSessions.length > 0 ? updatedSessions[0].id : null;
          }

          return {
            sessions: updatedSessions,
            chatMessages: restMessages,
            sessionConfigs: restConfigs,
            activeSessionId: newActiveSessionId,
          };
        });
      },

      updateSessionTitle: (sessionId, title) => {
        set((state) => ({
          sessions: state.sessions.map((session) =>
            session.id === sessionId ? { ...session, title } : session
          ),
        }));
      },

      setSessionMessages: (sessionId, messages) => {
        set((state) => ({
          chatMessages: { ...state.chatMessages, [sessionId]: messages },
        }));
      },

      setSessionConfig: (sessionId, config) => {
        set((state) => ({
          sessionConfigs: {
            ...state.sessionConfigs,
            [sessionId]: { ...(state.sessionConfigs[sessionId] || {}), ...config },
          },
        }));
      },
    }),
    {
      name: 'chat-storage',
      partialize: (state) => ({
        sessions: state.sessions,
        chatMessages: state.chatMessages,
        sessionConfigs: state.sessionConfigs,
        activeSessionId: state.activeSessionId,
      }),
    }
  )
);

export default useChatStore;
