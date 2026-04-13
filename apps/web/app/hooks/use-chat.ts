import dayjs from 'dayjs'
import { v4 as uuid } from 'uuid'
import { useImmer } from 'use-immer'
import invariant from 'tiny-invariant'
import { useCallback, useEffect, useEffectEvent, useRef, useState } from "react";

import { fetchSSE } from '~/lib/fetch-sse';
import type {
  AssistantMessage,
  UserMessage,
  UserMessageAttachment,
  StreamingStepRecord,
  RunningStepRecord,
  DoneStepRecord,
  ErrorStepRecord,
  ExportStepOutput,
  OutputFileInfo,
  StepName,
  StepRecord,
} from '~/components/llm-chat/message-list/types';
import { useAuthStore } from '~/stores/auth';

export type ChatMessage = UserMessage | AssistantMessage;

export interface InputType {
  text: string
  files: UserMessageAttachment[]
  thread_id?: string
}


// ========== 新架构 SSE 事件格式类型 ==========

interface ToolStartData {
  tool: string;
  args: Record<string, unknown>;
}

interface ToolStreamData {
  tool: string;
  delta: string;
  partial: string;
}

interface ToolEndData {
  tool: string;
  observation: string;
  data?: Record<string, unknown>;
}

interface AgentEndData {
  response: string;
}

interface SessionData {
  thread_id: string;
  is_new: boolean;
}

interface UseChatOptions {
  onStart?: () => void;
  initialMessages?: ChatMessage[];
  onSessionCreated?: (data: { thread_id: string; is_new: boolean }) => void;
  /** export 步骤完成时的回调，返回输出文件列表 */
  onExportSuccess?: (outputFiles: OutputFileInfo[]) => void;
}

/** 在数组中反向查找满足条件的元素的索引 */
function findLastIndex<T>(arr: T[], predicate: (el: T) => boolean): number {
  for (let i = arr.length - 1; i >= 0; i--) {
    if (predicate(arr[i])) return i;
  }
  return -1;
}

export const useChat = ({ onStart, initialMessages, onSessionCreated, onExportSuccess }: UseChatOptions) => {
  const [messages, updateMessages] = useImmer<AssistantMessage[]>(initialMessages as AssistantMessage[] || []);
  const [isProcessing, setIsProcessing] = useState(false);

  const abortRef = useRef<(() => void) | null>(null);

  const resetChat = useCallback(() => {
    abortRef.current?.();
    abortRef.current = null;
    updateMessages([]);
    setIsProcessing(false);
  }, []);

  useEffect(() => {
    return () => {
      abortRef.current?.();
    };
  }, []);

  const user = useAuthStore(state => state.user)

  const sendMessage = useEffectEvent(async ({ text, files, thread_id }: InputType) => {
    abortRef.current?.();

    invariant(user)

    const turnId = uuid()

    const userMessage: UserMessage = {
      id: `${turnId}:user`,
      role: "user",
      content: text,
      files,
      created: dayjs().unix(),
      avatar: user.avatar!
    };

    const assistantMessage: AssistantMessage = {
      id: `${turnId}:assistant`,
      role: "assistant",
      steps: [],
      status: 'pending',
    };

    updateMessages(draft => {
      draft.push(userMessage as unknown as AssistantMessage, assistantMessage)
    })

    setIsProcessing(true);

    const { abort } = fetchSSE({
      url: '/chat',
      body: {
        query: text,
        file_ids: files.map(item => item.id),
        thread_id: thread_id,
      },
      events: {
        onStart,

        onMessage: (event, rawData) => {
          const data = rawData as unknown as Record<string, unknown>;

          // ─── session 事件：会话元数据 ───
          if (event === "session") {
            const sessionData = data as unknown as SessionData;
            onSessionCreated?.({
              thread_id: sessionData.thread_id,
              is_new: sessionData.is_new,
            });
            return;
          }

          // ─── error 事件：系统/会话级错误 ───
          if (event === "error") {
            updateMessages(draft => {
              const lastMessage = draft[draft.length - 1];
              if (lastMessage && lastMessage.role === "assistant") {
                lastMessage.status = 'error';
                lastMessage.error = String(data.message || 'Unknown error');
              }
            });
            return;
          }

          // ─── tool_start 事件：工具开始调用 ───
          if (event === "tool_start") {
            const toolData = data as unknown as ToolStartData;
            const toolName: string = toolData.tool || "unknown";

            updateMessages(draft => {
              const lastMessage = draft[draft.length - 1];
              if (!lastMessage || lastMessage.role !== "assistant") return;

              lastMessage.status = 'streaming';

              // 避免重复创建同工具的 running 步骤
              const hasRunning = lastMessage.steps.some(
                (s) =>
                  s.step === toolName && s.status === "running"
              );
              if (hasRunning) return;

              const newStep: RunningStepRecord<StepName> = {
                step: toolName as StepName,
                status: "running",
                started_at: new Date().toISOString(),
              };
              lastMessage.steps.push(newStep as AssistantMessage["steps"][number]);
            });
            return;
          }

          // ─── tool_stream 事件：工具输出流式片段 ───
          if (event === "tool_stream") {
            const streamData = data as unknown as ToolStreamData;
            const toolName: string = streamData.tool || "unknown";
            const delta: string = streamData.delta || "";

            updateMessages(draft => {
              const lastMessage = draft[draft.length - 1];
              if (!lastMessage || lastMessage.role !== "assistant") return;

              lastMessage.status = 'streaming';

              // 找到当前工具的 running/streaming 步骤（反向找最后一个）
              const stepIndex = findLastIndex(
                lastMessage.steps,
                (s) => s.step === toolName && (s.status === "running" || s.status === "streaming")
              );

              if (stepIndex >= 0) {
                const existingStep = lastMessage.steps[stepIndex];
                const streamingStep: StreamingStepRecord<StepName> = {
                  ...(existingStep as StreamingStepRecord<StepName>),
                  status: "streaming",
                  streamContent: (existingStep as StreamingStepRecord<StepName>).streamContent
                    ? (existingStep as StreamingStepRecord<StepName>).streamContent + delta
                    : delta,
                };
                lastMessage.steps[stepIndex] = streamingStep as AssistantMessage["steps"][number];
              } else {
                // 无 running 步骤时，创建一个 streaming 步骤
                const streamingStep: StreamingStepRecord<StepName> = {
                  step: toolName as StepName,
                  status: "streaming",
                  started_at: new Date().toISOString(),
                  streamContent: delta,
                };
                lastMessage.steps.push(streamingStep as AssistantMessage["steps"][number]);
              }
            });
            return;
          }

          // ─── tool_end 事件：工具执行完成 ───
          if (event === "tool_end") {
            const endData = data as unknown as ToolEndData;
            const toolName: string = endData.tool || "unknown";
            const observation: string = endData.observation || "";

            updateMessages(draft => {
              const lastMessage = draft[draft.length - 1];
              if (!lastMessage || lastMessage.role !== "assistant") return;

              // 找到当前工具的 running/streaming 步骤
              const stepIndex = findLastIndex(
                lastMessage.steps,
                (s) => s.step === toolName && (s.status === "running" || s.status === "streaming")
              );

              if (stepIndex >= 0) {
                const existingStep = lastMessage.steps[stepIndex] as StreamingStepRecord<StepName>;
                const doneStep: DoneStepRecord<StepName> = {
                  step: toolName as StepName,
                  status: "done",
                  started_at: existingStep.started_at,
                  completed_at: new Date().toISOString(),
                  output: (observation || "") as unknown as DoneStepRecord<StepName>["output"],
                };
                lastMessage.steps[stepIndex] = doneStep as AssistantMessage["steps"][number];
              } else {
                // 没有对应步骤时，创建一个 done 步骤
                const doneStep: DoneStepRecord<StepName> = {
                  step: toolName as StepName,
                  status: "done",
                  started_at: new Date().toISOString(),
                  completed_at: new Date().toISOString(),
                  output: (observation || "") as unknown as DoneStepRecord<StepName>["output"],
                };
                lastMessage.steps.push(doneStep as AssistantMessage["steps"][number]);
              }

              // export_excel 工具完成后触发回调
              if (toolName === "export_excel" && endData.data) {
                const exportOutput = endData.data as unknown as ExportStepOutput;
                if (exportOutput.output_files?.length > 0) {
                  onExportSuccess?.(exportOutput.output_files);
                }
              }
            });
            return;
          }

          // ─── agent_end 事件：Agent 推理完成 ───
          if (event === "agent_end") {
            updateMessages(draft => {
              const lastMessage = draft[draft.length - 1];
              if (!lastMessage || lastMessage.role !== "assistant") return;
              if (lastMessage.status !== 'error') {
                lastMessage.status = 'done';
              }
            });
            return;
          }

          // ─── complete 事件：SSE 流结束 ───
          if (event === "complete") {
            updateMessages(draft => {
              const lastMessage = draft[draft.length - 1];
              if (lastMessage && lastMessage.role === "assistant") {
                if (lastMessage.status !== 'error') {
                  lastMessage.status = 'done';
                }
              }
            });
            return;
          }
        },

        onError: (err: Error) => {
          const message = err.message;
          updateMessages((draft) => {
            const lastMessage = draft[draft.length - 1]
            if (lastMessage && lastMessage.role === "assistant") {
              lastMessage.status = 'error'
              lastMessage.error = message
            }
          })
        },

        onFinally: () => {
          setIsProcessing(false);
        },

        onSuccess: () => {
          updateMessages((draft) => {
            const lastMessage = draft[draft.length - 1]
            if (lastMessage && lastMessage.role === "assistant") {
              if (lastMessage.status !== 'error') {
                lastMessage.status = 'done'
              }
            }
          });
        }
      },
    })

    abortRef.current = abort;
  });

  return {
    messages,
    isProcessing,
    resetChat,
    sendMessage,
    setMessages: updateMessages,
    clearMessages: useCallback(() => updateMessages([]), [updateMessages])
  };
}
