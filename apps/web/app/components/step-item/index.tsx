import { useState } from "react"
import { ChevronRight, ChevronDown, Loader2, CheckCircle2, XCircle, FileSpreadsheet, Brain, Code2, Play, AlertCircle } from "lucide-react"

import { cn } from "~/lib/utils"

import type {
  StepRecord,
  StepName,
  DoneStepRecord,
  StreamingStepRecord,
  LoadStepOutput,
  GenerateStepOutput,
  ValidateStepOutput,
  ExecuteStepOutput,
  ExportStepOutput
} from "~/components/llm-chat/message-list/types"

/** 步骤配置 */
const STEP_CONFIG: Record<StepName, { label: string; icon: React.ReactNode }> = {
  load: {
    label: "加载文件",
    icon: <FileSpreadsheet className="w-4 h-4" />,
  },
  generate: {
    label: "生成操作",
    icon: <Code2 className="w-4 h-4" />,
  },
  validate: {
    label: "验证操作",
    icon: <Brain className="w-4 h-4" />,
  },
  execute: {
    label: "执行处理",
    icon: <Play className="w-4 h-4" />,
  },
  export: {
    label: "导出文件",
    icon: <FileSpreadsheet className="w-4 h-4" />,
  },
  chat: {
    label: "AI 对话",
    icon: <Brain className="w-4 h-4" />,
  },
  analyze: {
    label: "分析数据",
    icon: <Brain className="w-4 h-4" />,
  },
}

/** 步骤名称列表 */
export const STEP_NAMES: StepName[] = ["load", "generate", "validate", "execute", "export"]

/** 单个步骤项组件 Props */
export interface StepItemProps {
  record: StepRecord
  defaultExpanded?: boolean
}

/** 单个步骤项组件 */
export const StepItem = ({ record, defaultExpanded = false }: StepItemProps) => {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded)

  const stepName = record.step
  const config = STEP_CONFIG[stepName]
  const status = record.status

  const isRunning = status === "running"
  const isStreaming = status === "streaming"
  const isDone = status === "done"
  const isError = status === "error"

  // 渲染状态图标
  const renderStatusIcon = () => {
    if (isRunning || isStreaming) {
      return <Loader2 className="w-4 h-4 text-brand animate-spin" />
    }
    if (isDone) {
      return <CheckCircle2 className="w-4 h-4 text-brand" />
    }
    if (isError) {
      return <XCircle className="w-4 h-4 text-error" />
    }
    return <div className="w-4 h-4 rounded-full border-2 border-gray-300" />
  }

  // 渲染流式内容（根据步骤类型使用不同组件）
  const renderStreamContent = (streamContent: string) => {
    if (!streamContent) return null

    if (stepName === "generate") {
      return (
        <div className="space-y-2 max-h-40 overflow-y-auto">
          <pre className="bg-gray-50 rounded-lg p-3 text-xs overflow-x-auto">
            {streamContent}
            <span className="inline-block w-2 h-4 bg-brand-light ml-0.5 animate-pulse" />
          </pre>
        </div>
      )
    }

    // 默认样式：适用于 load, validate, execute, export 等步骤
    return (
      <div className="text-sm text-gray-600">
        {streamContent}
        <span className="inline-block w-2 h-4 bg-emerald-500 ml-0.5 animate-pulse" />
      </div>
    )
  }

  // 渲染完成内容（根据步骤类型使用不同组件）
  const renderDoneContent = (doneRecord: DoneStepRecord) => {
    if (stepName === "load") {
      const output = doneRecord.output as LoadStepOutput
      const files = output?.files || []
      return (
        <div className="space-y-2">
          <p className="text-sm text-gray-600">
            已加载 {files.length} 个文件
          </p>
          {files.map((file) => (
            <div key={file.file_id} className="bg-gray-50 rounded-lg p-3">
              <p className="font-medium text-sm text-gray-800 mb-1">
                {file.filename}
              </p>
              {file.sheets.map((sheet) => (
                <div key={sheet.name} className="text-xs text-gray-500 mt-1">
                  <span className="font-medium">{sheet.name}</span>
                  <span className="mx-1">·</span>
                  <span>{sheet.row_count} 行</span>
                  <span className="mx-1">·</span>
                  <span>列：{sheet.columns.map(c => c.name).join("、")}</span>
                </div>
              ))}
            </div>
          ))}
        </div>
      )
    }

    if (stepName === "generate") {
      const output = doneRecord.output as GenerateStepOutput
      const operations = output?.operations || []
      return (
        <div className="space-y-2 max-h-50 overflow-y-auto">
          <pre className="bg-gray-50 rounded-lg p-3 text-xs overflow-x-auto">
            {JSON.stringify(operations, null, 2)}
          </pre>
        </div>
      )
    }

    if (stepName === "validate") {
      // 验证成功不显示内容，只有失败时才展开显示
      return null
    }

    if (stepName === "execute") {
      // 执行成功不显示内容，思路解读和快捷复现在后面单独显示
      return null
    }

    if (stepName === "export") {
      // 导出成功不显示内容，处理结果在后面单独显示
      return null
    }

    return null
  }

  // 获取内容
  const getContent = () => {
    if (isStreaming) {
      return renderStreamContent((record as StreamingStepRecord).streamContent || "")
    }
    if (isDone) {
      return renderDoneContent(record as DoneStepRecord)
    }
    if (isError && "error" in record) {
      return (
        <div className="text-sm text-error bg-error/10 rounded-lg px-3 py-2">
          {record.error?.message || "发生错误"}
        </div>
      )
    }
    return null
  }

  const content = getContent()
  const hasContent = content !== null

  // 获取错误信息 - 支持多种格式
  const getErrorMessage = () => {
    if (!isError) return null
    if ("error" in record && record.error) {
      // 标准格式: { code, message }
      if (typeof record.error === 'object' && 'message' in record.error) {
        return record.error.message
      }
      // 字符串格式
      if (typeof record.error === 'string') {
        return record.error
      }
      // 其他格式，尝试 JSON
      return JSON.stringify(record.error)
    }
    return "发生未知错误"
  }

  const errorMessage = getErrorMessage()

  // 错误状态下支持展开
  if (isError) {
    return (
      <div className="rounded-lg overflow-hidden bg-error/5 border border-error/20">
        <button
          type="button"
          onClick={() => setIsExpanded(!isExpanded)}
          className="w-full flex items-center gap-2 px-3 py-2 transition-colors hover:bg-error/10"
        >
          <span className="flex items-center justify-center w-6 h-6 rounded-full bg-error/10 text-error">
            {config.icon}
          </span>
          <span className="text-sm font-medium flex-1 text-error text-left">
            {config.label}
          </span>
          <XCircle className="w-4 h-4 text-error" />
          {isExpanded ? (
            <ChevronDown className="w-4 h-4 text-error/60" />
          ) : (
            <ChevronRight className="w-4 h-4 text-error/60" />
          )}
        </button>
        {isExpanded && errorMessage && (
          <div className="px-3 pb-3 pt-1">
            <div className="flex items-start gap-2 p-2 rounded-md bg-error/10">
              <AlertCircle className="w-4 h-4 text-error shrink-0 mt-0.5" />
              <p className="text-xs text-error break-all">{errorMessage}</p>
            </div>
          </div>
        )}
      </div>
    )
  }

  // 正常状态
  return (
    <div className={cn(
      "rounded-lg overflow-hidden transition-all",
      isDone && "bg-brand-muted/50",
      (isRunning || isStreaming) && "bg-brand-muted ring-1 ring-brand/30"
    )}>
      <button
        type="button"
        onClick={() => hasContent && setIsExpanded(!isExpanded)}
        disabled={!hasContent}
        className={cn(
          "w-full flex items-center gap-2 px-3 py-2 transition-colors",
          hasContent && "cursor-pointer hover:bg-black/5"
        )}
      >
        <span className={cn(
          "flex items-center justify-center w-6 h-6 rounded-full",
          isDone && "bg-brand-muted text-brand-dark",
          (isRunning || isStreaming) && "bg-brand-muted text-brand-dark"
        )}>
          {config.icon}
        </span>
        <span className={cn(
          "text-sm font-medium flex-1 text-left",
          isDone && "text-gray-700",
          (isRunning || isStreaming) && "text-brand-dark"
        )}>
          {config.label}
        </span>
        {renderStatusIcon()}
        {isExpanded ? (
          <ChevronDown className={cn("w-4 h-4 text-gray-400", !hasContent && "invisible")} />
        ) : (
          <ChevronRight className={cn("w-4 h-4 text-gray-400", !hasContent && "invisible")} />
        )}
      </button>
      {isExpanded && hasContent && (
        <div className="px-3 pb-3 pt-1">
          {content}
        </div>
      )}
    </div>
  )
}

export default StepItem

// 导出类型
export type { StepRecord, StepName }
