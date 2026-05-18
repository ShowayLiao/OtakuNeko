import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { v4 as uuidv4 } from 'uuid';

// 定义工具调用类型
export interface ToolCall {
  id: string; // 工具调用的唯一标识 (可以是工具名+时间戳)
  name: string; // 工具名称
  inputs?: any; // 传入的参数
  status: 'running' | 'success' | 'error';
  output?: any; // 工具的返回结果
}

// 定义消息类型
interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  createdAt: Date;
  extra?: any;
  toolCalls?: ToolCall[];
}

// 定义会话元数据类型
interface Session {
  id: string;
  title: string;
  updatedAt: Date;
}

// 定义聊天存储状态类型
interface ChatStore {
  // 数据结构
  sessions: Session[];
  chatMessages: Map<string, Message[]>;
  activeSessionId: string | null;

  // 核心 Action
  createSession: () => string;
  sendMessage: (sessionId: string, content: string | Message) => void;
  updateMessage: (sessionId: string, content: string, messageId?: string) => void;
  switchSession: (sessionId: string) => void;
  deleteSession: (sessionId: string) => void;
  updateSessionTitle: (sessionId: string, title: string) => void;
}

// 创建聊天存储
const useChatStore = create<ChatStore>()(
  persist(
    (set, get) => ({
      // 初始状态
      sessions: [],
      chatMessages: new Map(),
      activeSessionId: null,

      // 创建新会话
      createSession: () => {
        const sessionId = uuidv4();
        const newSession: Session = {
          id: sessionId,
          title: '新会话',
          updatedAt: new Date(),
        };

        set((state) => {
          // 创建新的聊天消息 Map，保留现有数据并添加新会话的空消息数组
          const newChatMessages = state.chatMessages && typeof state.chatMessages[Symbol.iterator] === 'function'
            ? new Map(state.chatMessages)
            : new Map();
          newChatMessages.set(sessionId, []);

          return {
            sessions: [...state.sessions, newSession],
            chatMessages: newChatMessages,
            activeSessionId: sessionId,
          };
        });

        return sessionId;
      },

      // 发送消息
      sendMessage: (sessionId, content, extra?: any) => {
        set((state) => {
          // 获取当前会话的消息
          const currentMessages = state.chatMessages && typeof state.chatMessages.get === 'function'
            ? state.chatMessages.get(sessionId) || []
            : [];

          // 创建或使用传入的消息对象
          let message: Message;
          if (typeof content === 'string') {
            // 如果是字符串，创建新的消息对象
            message = {
              id: uuidv4(),
              role: 'user',
              content,
              createdAt: new Date(),
              extra,
            };
          } else {
            // 如果是消息对象，直接使用
            message = content;
          }

          // 创建新的聊天消息 Map，添加消息
          const newChatMessages = state.chatMessages && typeof state.chatMessages[Symbol.iterator] === 'function'
            ? new Map(state.chatMessages)
            : new Map();
          newChatMessages.set(sessionId, [...currentMessages, message]);

          // 更新会话的 updatedAt
          const updatedSessions = state.sessions.map((session) =>
            session.id === sessionId
              ? { ...session, updatedAt: new Date() }
              : session
          );

          return {
            chatMessages: newChatMessages,
            sessions: updatedSessions,
          };
        });
      },

      // 更新消息（用于流式输出）
      updateMessage: (sessionId: string, content: string, messageId?: string, toolCallUpdate?: Partial<ToolCall>) => {
        set((state) => {
          // 获取当前会话的消息
          const currentMessages = state.chatMessages && typeof state.chatMessages.get === 'function'
            ? state.chatMessages.get(sessionId) || []
            : [];

          let updatedMessages = [...currentMessages];

          if (messageId) {
            // 如果提供了 messageId，更新指定的消息
            const messageIndex = updatedMessages.findIndex(msg => msg.id === messageId);
            if (messageIndex !== -1) {
              if (toolCallUpdate) {
                // 更新工具调用
                const currentMessage = updatedMessages[messageIndex];
                const currentToolCalls = currentMessage.toolCalls || [];
                const toolCallIndex = currentToolCalls.findIndex(tc => tc.id === toolCallUpdate.id);
                
                let updatedToolCalls;
                if (toolCallIndex !== -1) {
                  // 更新现有工具调用
                  updatedToolCalls = [...currentToolCalls];
                  updatedToolCalls[toolCallIndex] = {
                    ...updatedToolCalls[toolCallIndex],
                    ...toolCallUpdate,
                  };
                } else {
                  // 添加新工具调用
                  updatedToolCalls = [...currentToolCalls, toolCallUpdate];
                }
                
                updatedMessages[messageIndex] = {
                  ...currentMessage,
                  toolCalls: updatedToolCalls as ToolCall[],
                };
              } else {
                // 更新消息内容
                updatedMessages[messageIndex] = {
                  ...updatedMessages[messageIndex],
                  content,
                };
              }
            } else {
              // 如果找不到指定的消息，添加一个新的助手消息
              const assistantMessage: Message = {
                id: uuidv4(),
                role: 'assistant',
                content: content || '',
                createdAt: new Date(),
                toolCalls: toolCallUpdate ? [toolCallUpdate as ToolCall] : undefined,
              };
              updatedMessages.push(assistantMessage);
            }
          } else {
            // 如果没有提供 messageId，检查最后一条消息是否是助手消息
            const lastMessage = updatedMessages[updatedMessages.length - 1];
            if (!lastMessage || lastMessage.role !== 'assistant') {
              // 如果最后一条消息不是助手消息，则添加一个新的助手消息
              const assistantMessage: Message = {
                id: uuidv4(),
                role: 'assistant',
                content: content || '',
                createdAt: new Date(),
                toolCalls: toolCallUpdate ? [toolCallUpdate as ToolCall] : undefined,
              };
              updatedMessages.push(assistantMessage);
            } else {
              // 更新最后一条消息
              if (toolCallUpdate) {
                // 更新工具调用
                const currentToolCalls = lastMessage.toolCalls || [];
                const toolCallIndex = currentToolCalls.findIndex(tc => tc.id === toolCallUpdate.id);
                
                let updatedToolCalls;
                if (toolCallIndex !== -1) {
                  // 更新现有工具调用
                  updatedToolCalls = [...currentToolCalls];
                  updatedToolCalls[toolCallIndex] = {
                    ...updatedToolCalls[toolCallIndex],
                    ...toolCallUpdate,
                  };
                } else {
                  // 添加新工具调用
                  updatedToolCalls = [...currentToolCalls, toolCallUpdate];
                }
                
                updatedMessages[updatedMessages.length - 1] = {
                  ...lastMessage,
                  toolCalls: updatedToolCalls as ToolCall[],
                };
              } else {
                // 更新消息内容
                updatedMessages[updatedMessages.length - 1] = {
                  ...lastMessage,
                  content,
                };
              }
            }
          }

          // 创建新的聊天消息 Map
          const newChatMessages = state.chatMessages && typeof state.chatMessages[Symbol.iterator] === 'function'
            ? new Map(state.chatMessages)
            : new Map();
          newChatMessages.set(sessionId, updatedMessages);

          // 更新会话的 updatedAt
          const updatedSessions = state.sessions.map((session) =>
            session.id === sessionId
              ? { ...session, updatedAt: new Date() }
              : session
          );

          return {
            chatMessages: newChatMessages,
            sessions: updatedSessions,
          };
        });
      },

      // 切换会话
      switchSession: (sessionId) => {
        set(() => ({
          activeSessionId: sessionId,
        }));
      },

      // 删除会话
      deleteSession: (sessionId) => {
        set((state) => {
          // 过滤掉要删除的会话
          const updatedSessions = state.sessions.filter(
            (session) => session.id !== sessionId
          );

          // 创建新的聊天消息 Map，删除对应会话的消息
          const newChatMessages = state.chatMessages && typeof state.chatMessages[Symbol.iterator] === 'function'
            ? new Map(state.chatMessages)
            : new Map();
          newChatMessages.delete(sessionId);

          // 如果删除的是当前激活的会话，则切换到第一个会话
          let newActiveSessionId = state.activeSessionId;
          if (state.activeSessionId === sessionId) {
            newActiveSessionId = updatedSessions.length > 0 ? updatedSessions[0].id : null;
          }

          return {
            sessions: updatedSessions,
            chatMessages: newChatMessages,
            activeSessionId: newActiveSessionId,
          };
        });
      },

      // 更新会话标题
      updateSessionTitle: (sessionId, title) => {
        set((state) => {
          const updatedSessions = state.sessions.map((session) =>
            session.id === sessionId ? { ...session, title } : session
          );

          return {
            sessions: updatedSessions,
          };
        });
      },
    }),
    {
      name: 'chat-storage',
      partialize: (state) => ({
        sessions: state.sessions,
        chatMessages: Object.fromEntries(state.chatMessages),
        activeSessionId: state.activeSessionId,
      }),
      merge: (persisted: any, current: any) => ({
        ...current,
        sessions: persisted.sessions || [],
        chatMessages: persisted.chatMessages
          ? new Map(Object.entries(persisted.chatMessages))
          : new Map(),
        activeSessionId: persisted.activeSessionId || null,
      }),
    }
  )
);

export default useChatStore;
export type { Message, Session };
