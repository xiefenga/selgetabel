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
  StepName,
  SessionEventData,
  StepEventData,
  ErrorEventData,
  StreamingStepRecord,
  RunningStepRecord,
  DoneStepRecord,
  ErrorStepRecord,
} from '~/components/llm-chat/message-list/types';
import { useAuthStore } from '~/stores/auth';

export type ChatMessage = UserMessage | AssistantMessage;

export interface InputType {
  text: string
  files: UserMessageAttachment[]
  thread_id?: string
}



/** 步骤名称列表（用于验证） */
const STEP_NAMES: StepName[] = ["load", "analyze", "generate", "execute"];

/** 判断是否为有效的步骤名称 */
function isStepName(step: string): step is StepName {
  return STEP_NAMES.includes(step as StepName);
}

interface UseChatOptions {
  onStart?: () => void;
  initialMessages?: ChatMessage[];
  onSessionCreated?: (data: SessionEventData) => void;
}

export const useChat = ({ onStart, initialMessages, onSessionCreated }: UseChatOptions) => {
  const [messages, updateMessages] = useImmer<ChatMessage[]>(initialMessages || []);
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
      completed: dayjs().unix()
    };

    updateMessages(draft => {
      draft.push(userMessage, assistantMessage)
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
        onMessage: (event, data) => {
          // 处理 session 事件 - 会话元数据
          if (event === "session") {
            const sessionData = data as SessionEventData;
            onSessionCreated?.(sessionData);
            return;
          }

          // 处理 error 事件 - 会话级/系统级错误
          if (event === "error") {
            const errorData = data as ErrorEventData;
            updateMessages(draft => {
              const lastMessage = draft[draft.length - 1];
              if (lastMessage && lastMessage.role === "assistant") {
                lastMessage.status = 'error';
                lastMessage.error = errorData.message;
              }
            });
            return;
          }

          // 处理默认 message 事件 - 步骤状态更新
          const stepData = data as StepEventData;
          const { step, status, delta, output, error } = stepData;

          // 处理 complete 特殊步骤
          if (step === "complete" && status === "done") {
            updateMessages(draft => {
              const lastMessage = draft[draft.length - 1];
              if (lastMessage && lastMessage.role === "assistant") {
                lastMessage.status = 'done';
                lastMessage.completed = dayjs().unix();
              }
            });
            return;
          }

          // 验证步骤名称
          if (!isStepName(step)) {
            console.warn(`Unknown step: ${step}`);
            return;
          }

          updateMessages(draft => {
            const lastMessage = draft[draft.length - 1];
            if (!lastMessage || lastMessage.role !== "assistant") return;

            const assistantMsg = lastMessage as AssistantMessage;
            assistantMsg.status = 'streaming';

            // 查找当前步骤的最后一条记录（使用 reduce 替代 findLastIndex）
            const existingStepIndex = assistantMsg.steps.reduce<number>(
              (lastIndex, s, idx) => (s.step === step ? idx : lastIndex),
              -1
            );

            switch (status) {
              case "running": {
                // 新步骤开始
                const newStep: RunningStepRecord = {
                  step,
                  status: "running",
                  started_at: new Date().toISOString(),
                };
                assistantMsg.steps.push(newStep);
                break;
              }

              case "streaming": {
                // 流式输出
                if (existingStepIndex >= 0) {
                  const existingStep = assistantMsg.steps[existingStepIndex];
                  // 转换为 streaming 状态并累积内容
                  const streamingStep: StreamingStepRecord = {
                    ...existingStep,
                    status: "streaming",
                    streamContent: (existingStep as StreamingStepRecord).streamContent
                      ? (existingStep as StreamingStepRecord).streamContent + (delta || "")
                      : (delta || ""),
                  };
                  assistantMsg.steps[existingStepIndex] = streamingStep;
                }
                break;
              }

              case "done": {
                // 步骤完成
                if (existingStepIndex >= 0) {
                  const existingStep = assistantMsg.steps[existingStepIndex];
                  const doneStep: DoneStepRecord = {
                    step,
                    status: "done",
                    started_at: existingStep.started_at,
                    completed_at: new Date().toISOString(),
                    output: output as DoneStepRecord["output"],
                  };
                  assistantMsg.steps[existingStepIndex] = doneStep;

                  // 如果是 execute 步骤完成，触发回调
                  if (step === "execute" && output) {
                    const execOutput = output as {
                      output_file?: string;
                      formulas?: unknown[];
                    };
                  }
                }
                break;
              }

              case "error": {
                // 步骤失败
                if (existingStepIndex >= 0) {
                  const existingStep = assistantMsg.steps[existingStepIndex];
                  const errorStep: ErrorStepRecord = {
                    step,
                    status: "error",
                    started_at: existingStep.started_at,
                    completed_at: new Date().toISOString(),
                    error: error || { code: "UNKNOWN", message: "未知错误" },
                  };
                  assistantMsg.steps[existingStepIndex] = errorStep;
                  assistantMsg.status = 'error';
                  assistantMsg.error = error?.message;
                }
                break;
              }
            }
          });
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
              // 只有不是 error 状态时才设置为 done
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
