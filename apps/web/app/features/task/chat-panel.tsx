import dayjs from 'dayjs'
import { useState, useMemo, useRef, useEffect, useImperativeHandle, useCallback } from 'react'
import { RefreshCw, Sparkles, Download, Lightbulb, ListChecks, AlertCircle, FileSpreadsheet, Activity, Clock, Loader2 } from 'lucide-react'

import { Button } from '~/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '~/components/ui/dialog'

import TaskInput from './task-input'
import UserMessageCard from './user-message-card'
import { StepItem } from '~/components/step-item'
import ExcelPreview from '~/components/excel-preview'
import InsightCard from '~/components/insight-card'
import ExcelIcon from '~/assets/iconify/vscode-icons/file-type-excel.svg?react'
import { Streamdown } from 'streamdown'

import { cn } from '~/lib/utils'

import type { FileItem } from '~/components/file-item-badge'
import type { UseFileUploadReturn } from '~/hooks/use-file-upload'
import type { StepRecord, DoneStepRecord, ExecuteStepOutput, UserMessageAttachment, OutputFileInfo } from '~/components/llm-chat/message-list/types'

// ========== 多轮对话类型定义 ==========

/** 用户消息 */
export interface UserMessage {
  id: string
  role: 'user'
  content: string
  files: UserMessageAttachment[]
  timestamp: number
}

/** AI 响应 */
export interface AssistantMessage {
  id: string
  role: 'assistant'
  /** 处理步骤 */
  steps: StepRecord[]
  /** 本轮状态 */
  status: 'pending' | 'streaming' | 'done' | 'error'
  /** 错误信息 */
  error?: string
  /** 输出文件 */
  outputFiles: OutputFileInfo[]
  /** 思路解读 */
  strategy?: string
  /** 快捷复现 */
  manualSteps?: string
  /** 开始时间 */
  startedAt?: number
  /** 完成时间 */
  completedAt?: number
}

/** 对话轮次 */
export interface ConversationTurn {
  id: string
  userMessage: UserMessage
  assistantMessage?: AssistantMessage
}

export interface ChatPanelProps {
  // ========== 对话历史 ==========
  /** 对话轮次列表（按时间顺序） */
  turns: ConversationTurn[]

  // ========== 当前输入状态 ==========
  /** 文件上传相关 */
  fileUpload: UseFileUploadReturn
  /** 当前输入的需求描述 */
  query: string
  /** 需求描述变更 */
  onQueryChange: (query: string) => void

  // ========== 当前活跃轮次 ==========
  /** 当前正在处理的轮次 ID（null 表示空闲状态） */
  activeTurnId: string | null
  /** 是否正在处理 */
  isProcessing: boolean

  // ========== 操作回调 ==========
  /** 提交新一轮任务 */
  onSubmit: () => void
  /** 重试指定轮次 */
  onRetry?: (turnId: string) => void
  /** 取消当前处理 */
  onCancel?: () => void
  /** 清空对话，开始新任务 */
  onClear?: () => void

  // ========== 文件上下文 ==========
  /** 当前可用的文件上下文（历史轮次的输出文件，可被后续轮次引用） */
  availableFiles?: OutputFileInfo[]
  /** 选中作为输入的历史文件 ID */
  selectedHistoryFiles?: string[]
  /** 切换历史文件选中状态 */
  onToggleHistoryFile?: (fileId: string) => void

  // ========== UI 配置 ==========
  /** 用户头像 */
  userAvatar?: string
  /** ref handle */
  ref?: React.Ref<ChatPanelHandle>
}

export interface ChatPanelHandle {
  scrollToBottom: () => void
}

/** 计算步骤耗时 */
const calculateDuration = (steps: StepRecord[]): string | null => {
  if (steps.length === 0) return null

  const firstStep = steps.find(s => s.started_at)
  const completedSteps = steps.filter(s => s.completed_at)
  const lastStep = completedSteps[completedSteps.length - 1]

  if (!firstStep?.started_at || !lastStep?.completed_at) return null

  const start = dayjs(firstStep.started_at)
  const end = dayjs(lastStep.completed_at)
  const diffMs = end.diff(start)

  if (diffMs < 1000) {
    return `${diffMs}ms`
  } else if (diffMs < 60000) {
    return `${(diffMs / 1000).toFixed(1)}s`
  } else {
    const minutes = Math.floor(diffMs / 60000)
    const seconds = Math.floor((diffMs % 60000) / 1000)
    return `${minutes}m ${seconds}s`
  }
}

/** 右侧对话面板组件 */
const ChatPanel = ({
  turns,
  fileUpload,
  query,
  onQueryChange,
  activeTurnId,
  isProcessing,
  onSubmit,
  onRetry,
  onCancel,
  availableFiles = [],
  selectedHistoryFiles = [],
  onToggleHistoryFile,
  userAvatar,
  ref,
}: ChatPanelProps) => {
  const {
    fileItems,
    isUploading,
    removeFile,
    retryUploadFile,
    uploadFilesBatch,
  } = fileUpload

  const [previewFile, setPreviewFile] = useState<FileItem | null>(null)

  // ========== 自动滚动 ==========
  const scrollRef = useRef<HTMLDivElement>(null)
  const isSticky = useRef(true)

  const scrollToBottom = useCallback(() => {
    const el = scrollRef.current
    if (!el) return
    isSticky.current = true
    requestAnimationFrame(() => {
      el.scrollTo({ top: el.scrollHeight })
    })
  }, [])

  const handleScroll = useCallback(() => {
    const el = scrollRef.current
    if (!el) return
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 50
    isSticky.current = atBottom
  }, [])

  // 暴露 scrollToBottom 给父组件
  useImperativeHandle(ref, () => ({ scrollToBottom }), [scrollToBottom])

  // 流式响应期间，sticky 时跟随滚动
  useEffect(() => {
    if (isProcessing && isSticky.current) {
      scrollToBottom()
    }
  }, [turns, isProcessing, scrollToBottom])

  // 是否为空对话（无历史轮次）
  const isEmptyConversation = turns.length === 0

  // 是否可以提交：
  // - 允许纯文本聊天，不强制要求文件
  // - 如果有文件，可以处理文件；如果没有文件，可以进行纯文本对话
  const canSubmit = useMemo(() => {
    if (isProcessing || isUploading) return false
    if (!query.trim()) return false
    
    // 允许纯文本聊天，不强制要求文件
    return true
  }, [isProcessing, isUploading, query])

  // 添加文件
  const handleAddFiles = (files: File[]) => {
    uploadFilesBatch(files)
  }

  // 是否显示输入区的文件列表（有新上传的文件时显示）
  const showInputFiles = fileItems.length > 0

  return (
    <div className="h-full flex flex-col bg-linear-to-br from-slate-50 via-white to-brand-muted/20">
      {/* 滚动内容区 */}
      <div ref={scrollRef} onScroll={handleScroll} className="flex-1 overflow-y-auto">
        <div className="p-5 space-y-4">
          {/* 欢迎信息（仅在空对话且无上传文件时显示） */}
          {isEmptyConversation && fileItems.length === 0 && (
            <div className="text-center py-8">
              <div className="inline-flex items-center justify-center w-14 h-14 rounded-full bg-brand-muted mb-3">
                <Sparkles className="w-7 h-7 text-brand" />
              </div>
              <h1 className="text-xl font-bold bg-linear-to-r from-emerald-700 to-teal-700 bg-clip-text text-transparent mb-1.5">
                Excel 智能处理
              </h1>
              <p className="text-gray-500 text-sm">
                上传文件，描述需求，AI 自动处理
              </p>
            </div>
          )}

          {/* 多轮对话渲染 */}
          {turns.map((turn, index) => (
            <TurnRenderer
              key={turn.id}
              turn={turn}
              userAvatar={userAvatar}
              isActive={isProcessing && index === turns.length - 1}
              onRetry={onRetry}
            />
          ))}
        </div>
      </div>

      {/* 底部输入区 */}
      <div className="shrink-0 p-4 pt-3 bg-white/80 backdrop-blur-sm">
        {/* 输入框 */}
        <TaskInput
          value={query}
          onChange={onQueryChange}
          onSubmit={onSubmit}
          onStop={onCancel}
          files={showInputFiles ? fileItems : []}
          onAddFiles={handleAddFiles}
          onRemoveFile={removeFile}
          onRetryFile={retryUploadFile}
          disabled={false}
          isProcessing={isProcessing}
          canSubmit={canSubmit}
          placeholder={isEmptyConversation ? "描述你的处理需求..." : "继续描述你的需求..."}
        />
      </div>

      {/* Excel 预览弹窗 */}
      <Dialog open={!!previewFile} onOpenChange={(open) => !open && setPreviewFile(null)}>
        <DialogContent className="max-w-[95vw]! max-h-[95vh]! w-[95vw]! h-[95vh]! flex flex-col p-0 gap-0">
          <DialogHeader className="px-6 pt-6 pb-4 border-b shrink-0">
            <DialogTitle>
              <div className="flex items-center gap-0.5">
                <ExcelIcon className="w-6 h-6 shrink-0" />
                <div>{previewFile?.file.name}</div>
              </div>
            </DialogTitle>
          </DialogHeader>
          <div className="flex-1 overflow-hidden min-h-0">
            {previewFile && previewFile.path && (
              <ExcelPreview className="w-full h-full" fileUrl={previewFile.path} />
            )}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}

/** 单轮对话渲染组件 */
const TurnRenderer = ({
  turn,
  userAvatar,
  isActive,
  onRetry,
}: {
  turn: ConversationTurn
  userAvatar?: string
  isActive: boolean
  onRetry?: (turnId: string) => void
}) => {
  const { userMessage, assistantMessage } = turn

  // 从 execute 步骤提取思路解读和快捷复现
  const executeOutput = useMemo(() => {
    if (!assistantMessage) return null
    const executeStep = assistantMessage.steps.find(
      s => s.step === 'execute' && s.status === 'done'
    ) as DoneStepRecord | undefined
    return executeStep?.output as ExecuteStepOutput | null
  }, [assistantMessage])

  // 是否处于等待响应状态（已发送消息，但 AI 尚未开始返回可见内容）
  const isWaitingResponse = isActive && (
    !assistantMessage ||
    assistantMessage.steps.length === 0 ||
    // chat 步骤已创建但尚无实际文本（等待 LLM 首个 token）
    (assistantMessage.steps.length > 0 && assistantMessage.steps.every(s =>
      s.step === 'chat' && (
        s.status === 'running' ||
        (s.status === 'streaming' && !(s as any).streamContent)
      )
    ))
  )

  // 状态判断
  const hasSteps = assistantMessage && assistantMessage.steps.length > 0
  const isAllDone = assistantMessage?.status === 'done' && hasSteps
  const hasError = assistantMessage?.status === 'error' || assistantMessage?.steps.some(s => s.status === 'error')
  const hasOutputFiles = assistantMessage && assistantMessage.outputFiles.length > 0

  // 计算耗时和完成时间
  const duration = useMemo(() => {
    if (!assistantMessage) return null
    return calculateDuration(assistantMessage.steps)
  }, [assistantMessage])

  const formattedCompletedTime = assistantMessage?.completedAt
    ? dayjs.unix(assistantMessage.completedAt).format('YYYY-MM-DD HH:mm')
    : null

  return (
    <div className={cn("space-y-4", isActive && "animate-pulse-subtle")}>
      {/* 用户消息 */}
      <UserMessageCard
        content={userMessage.content}
        files={userMessage.files}
        timestamp={userMessage.timestamp}
        avatar={userAvatar}
      />

      {/* 等待响应 loading */}
      {isWaitingResponse && (
        <div className="flex items-center gap-2.5 py-3 px-1">
          <Loader2 className="w-4 h-4 text-brand animate-spin" />
          <span className="text-sm text-gray-500">正在思考</span>
          <span className="flex gap-0.5">
            <span className="w-1 h-1 rounded-full bg-gray-400 animate-bounce [animation-delay:0ms]" />
            <span className="w-1 h-1 rounded-full bg-gray-400 animate-bounce [animation-delay:150ms]" />
            <span className="w-1 h-1 rounded-full bg-gray-400 animate-bounce [animation-delay:300ms]" />
          </span>
        </div>
      )}

      {/* AI 响应 */}
      {assistantMessage && (
        <>
          {/* 步骤列表 */}
          {hasSteps && (
            <section className="space-y-2">
              {assistantMessage.steps.map((record, index) => {
                // ==========================================
                // 💡 重点修改位置：拦截纯文本回复类步骤，用普通文本渲染（不显示步骤栏）
                // ==========================================
                const CHAT_LIKE_STEPS = ['chat', 'analyze', 'hello', 'clarify'];
                if (CHAT_LIKE_STEPS.includes(record.step)) {
                  let content = '';
                  if (record.status === 'streaming') {
                    content = (record as any).streamContent || '';
                  } else if (record.status === 'done') {
                    // chat: output is string directly
                    // analyze: output is AnalyzeStepOutput with content field
                    const output = (record as any).output;
                    if (typeof output === 'string') {
                      content = output;
                    } else if (output && typeof output.content === 'string') {
                      content = output.content;
                    }
                  }

                  const isStreaming = record.status === 'streaming';

                  return (
                    <div
                      key={`${record.step}-${index}`}
                      className="text-sm text-gray-800 leading-relaxed py-2 px-1"
                    >
                      <Streamdown
                        mode={isStreaming ? 'streaming' : 'static'}
                        caret={isStreaming ? 'block' : undefined}
                      >
                        {typeof content === 'string' ? content : ''}
                      </Streamdown>
                    </div>
                  );
                }

                // ==========================================
                // 非 chat 步骤 (如 generate, execute) 依然交给 StepItem 渲染
                // ==========================================
                return (
                  <StepItem
                    key={`${record.step}-${index}`}
                    record={record}
                  />
                );
              })}

              {/* 全局错误 */}
              {assistantMessage.status === 'error' && assistantMessage.error && (
                <div className="flex items-start gap-2 p-3 rounded-lg bg-error/10 border border-error/20">
                  <AlertCircle className="w-4 h-4 text-error shrink-0 mt-0.5" />
                  <p className="text-xs text-error">{assistantMessage.error}</p>
                </div>
              )}
            </section>
          )}

          {/* 思路解读和快捷复现 */}
          {executeOutput && (executeOutput.strategy || executeOutput.manual_steps) && (
            <section className="space-y-3">
              {executeOutput.strategy && (
                <InsightCard
                  icon={<Lightbulb className="w-4 h-4" />}
                  title="思路解读"
                  content={executeOutput.strategy}
                  variant="info"
                  defaultExpanded
                />
              )}
              {executeOutput.manual_steps && (
                <InsightCard
                  icon={<ListChecks className="w-4 h-4" />}
                  title="快捷复现"
                  content={executeOutput.manual_steps}
                  variant="warning"
                  defaultExpanded
                />
              )}
            </section>
          )}

          {/* 结果下载 */}
          {isAllDone && hasOutputFiles && (
            <section className="space-y-3">
              <h3 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
                <Download className="w-4 h-4 text-brand" />
                处理结果
                {assistantMessage.outputFiles.length > 1 && (
                  <span className="px-1.5 py-0.5 text-xs rounded-full bg-brand/10 text-brand-dark">
                    {assistantMessage.outputFiles.length}
                  </span>
                )}
              </h3>
              <div className="space-y-2">
                {assistantMessage.outputFiles.map((file) => (
                  <div
                    key={file.file_id}
                    className="flex items-center gap-3 p-3 rounded-xl bg-brand-muted/30 border border-brand/20"
                  >
                    <div className="w-10 h-10 rounded-lg bg-brand-muted flex items-center justify-center">
                      <ExcelIcon className="w-5 h-5 text-brand" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-gray-900 truncate">{file.filename}</p>
                      <p className="text-xs text-gray-500">处理完成</p>
                    </div>
                    <Button
                      size="sm"
                      asChild
                      className="bg-brand hover:bg-brand-dark text-white"
                    >
                      <a href={file.url} download={file.filename}>
                        <Download className="w-4 h-4" />
                      </a>
                    </Button>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* 处理摘要 */}
          {(isAllDone || hasError) && hasSteps && (
            <div className="flex items-center justify-between">
              <ProcessingSummary
                hasError={!!hasError}
                duration={duration}
                completedTime={formattedCompletedTime}
              />
              {/* 重试按钮 */}
              {hasError && onRetry && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => onRetry(turn.id)}
                  className="text-gray-500 hover:text-gray-700"
                >
                  <RefreshCw className="w-3.5 h-3.5 mr-1" />
                  重试
                </Button>
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}

/** 处理摘要组件 */
const ProcessingSummary = ({
  hasError,
  duration,
  completedTime,
}: {
  hasError: boolean
  duration: string | null
  completedTime: string | null
}) => (
  <div className="flex items-center gap-2 text-gray-400 text-xs pt-1">
    {/* 耗时 */}
    {duration && (
      <div className="flex items-center gap-1 text-gray-400 text-sm">
        <Activity className="w-3.5 h-3.5 text-gray-400" />
        <span>{duration}</span>
      </div>
    )}

    {/* 完成时间 */}
    {completedTime && (
      <div className="flex items-center gap-1 text-gray-400 text-sm">
        <Clock className="w-3.5 h-3.5" />
        <span>{completedTime}</span>
      </div>
    )}
  </div>
)

export default ChatPanel