import { Streamdown } from 'streamdown';
import { useState } from "react";
import { ChevronRight, Loader2, CheckCircle2, XCircle, FileSpreadsheet, Brain, Code2, Play, Sparkles } from "lucide-react";

import { cn } from "~/lib/utils";

import type {
  AssistantMessage as AssistantMessageType,
  StepRecord,
  StepName,
  DoneStepRecord,
  StreamingStepRecord,
  LoadStepOutput,
  GenerateStepOutput,
  ValidateStepOutput,
  ExecuteStepOutput,
  ExportStepOutput
} from "../types";

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
};

/** 单个步骤项组件 */
interface StepItemProps {
  record: StepRecord;
  defaultExpanded?: boolean;
}

const StepItem = ({ record, defaultExpanded = false }: StepItemProps) => {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);

  const stepName = record.step;
  const config = STEP_CONFIG[stepName];
  const status = record.status;

  const isRunning = status === "running";
  const isStreaming = status === "streaming";
  const isDone = status === "done";
  const isError = status === "error";

  // 渲染状态图标
  const renderStatusIcon = () => {
    if (isRunning || isStreaming) {
      return <Loader2 className="w-4 h-4 text-emerald-600 animate-spin" />;
    }
    if (isDone) {
      return <CheckCircle2 className="w-4 h-4 text-emerald-600" />;
    }
    if (isError) {
      return <XCircle className="w-4 h-4 text-red-500" />;
    }
    return <div className="w-4 h-4 rounded-full border-2 border-gray-300" />;
  };

  // 渲染流式内容（根据步骤类型使用不同组件）
  const renderStreamContent = (streamContent: string) => {
    if (!streamContent) return null;

    if (stepName === "generate") {
      return (
        <div className="space-y-2">
          <p className="text-sm text-gray-600">正在生成操作...</p>
          <pre className="bg-gray-50 rounded-lg p-3 text-xs overflow-x-auto">
            {streamContent}
            <span className="inline-block w-2 h-4 bg-emerald-500 ml-0.5 animate-pulse" />
          </pre>
        </div>
      );
    }

    // 默认样式：适用于 load, validate, execute, export 等步骤
    return (
      <div className="text-sm text-gray-600">
        {streamContent}
        <span className="inline-block w-2 h-4 bg-emerald-500 ml-0.5 animate-pulse" />
      </div>
    );
  };

  // 渲染完成内容（根据步骤类型使用不同组件）
  const renderDoneContent = (doneRecord: DoneStepRecord) => {
    if (stepName === "load") {
      const output = doneRecord.output as LoadStepOutput;
      const files = output?.files || [];
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
      );
    }

    if (stepName === "generate") {
      const output = doneRecord.output as GenerateStepOutput;
      const operations = output?.operations || [];
      return (
        <div className="space-y-2">
          <p className="text-sm text-gray-600">
            生成了 {operations.length} 个操作
          </p>
          <pre className="bg-gray-50 rounded-lg p-3 text-xs overflow-x-auto">
            {JSON.stringify(operations, null, 2)}
          </pre>
        </div>
      );
    }

    if (stepName === "validate") {
      const output = doneRecord.output as ValidateStepOutput;
      return (
        <div className="text-sm text-gray-600">
          {output?.valid ? "验证通过" : "验证失败"}
        </div>
      );
    }

    if (stepName === "execute") {
      const output = doneRecord.output as ExecuteStepOutput;
      const { strategy, manual_steps } = output;
      return (
        <div className="space-y-4">
          {/* 思路解读 */}
          {strategy && (
            <div className="border border-blue-200 rounded-lg overflow-hidden">
              <div className="bg-blue-50 px-3 py-2 border-b border-blue-200">
                <span className="text-sm font-medium text-blue-700">思路解读</span>
              </div>
              <pre className="text-sm p-3 whitespace-pre-wrap font-sans text-gray-700">
                {strategy}
              </pre>
            </div>
          )}

          {/* 快捷复现 */}
          {manual_steps && (
            <details className="border border-amber-200 rounded-lg overflow-hidden">
              <summary className="bg-amber-50 px-3 py-2 cursor-pointer text-sm font-medium text-amber-700 hover:bg-amber-100">
                快捷复现（点击展开）
              </summary>
              <pre className="text-sm p-3 whitespace-pre-wrap font-sans text-gray-700 border-t border-amber-200">
                {manual_steps}
              </pre>
            </details>
          )}
        </div>
      );
    }

    if (stepName === "export") {
      const output = doneRecord.output as ExportStepOutput;
      const outputFiles = output?.output_files || [];
      return (
        <div className="space-y-2">
          {outputFiles.map((file) => (
            <a
              key={file.file_id}
              href={file.url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 text-emerald-700 bg-emerald-50 rounded-lg px-3 py-2 hover:bg-emerald-100 transition-colors"
            >
              <FileSpreadsheet className="w-4 h-4" />
              <span className="text-sm font-medium">{file.filename}</span>
            </a>
          ))}
        </div>
      );
    }

    return null;
  };

  // 获取内容
  const getContent = () => {
    if (isStreaming) {
      return renderStreamContent((record as StreamingStepRecord).streamContent || "");
    }
    if (isDone) {
      return renderDoneContent(record as DoneStepRecord);
    }
    if (isError && "error" in record) {
      return (
        <div className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">
          {record.error?.message || "发生错误"}
        </div>
      );
    }
    return null;
  };

  const content = getContent();
  const hasContent = content !== null;

  return (
    <div className={cn(
      "border rounded-lg transition-all",
      isError ? "border-red-200 bg-red-50/50" : "border-gray-200 bg-white",
      (isRunning || isStreaming) && "ring-2 ring-emerald-500/20"
    )}>
      {/* 头部 */}
      <button
        type="button"
        onClick={() => hasContent && setIsExpanded(!isExpanded)}
        className={cn(
          "w-full flex items-center gap-3 px-4 py-3 text-left",
          hasContent && "cursor-pointer hover:bg-gray-50/50"
        )}
        disabled={!hasContent}
      >
        {/* 展开/收起图标 */}
        <ChevronRight
          className={cn(
            "w-4 h-4 text-gray-400 transition-transform",
            isExpanded && "rotate-90",
            !hasContent && "invisible"
          )}
        />

        {/* 步骤图标 */}
        <span className={cn(
          "flex items-center justify-center w-8 h-8 rounded-full",
          isDone && "bg-emerald-100 text-emerald-700",
          isError && "bg-red-100 text-red-600",
          (isRunning || isStreaming) && "bg-emerald-100 text-emerald-700"
        )}>
          {config.icon}
        </span>

        {/* 步骤名称 */}
        <span className={cn(
          "flex-1 text-sm font-medium",
          isDone && "text-gray-900",
          isError && "text-red-700",
          (isRunning || isStreaming) && "text-emerald-700"
        )}>
          {config.label}
          {(isRunning || isStreaming) && (
            <span className="ml-2 text-emerald-600 font-normal">处理中...</span>
          )}
        </span>

        {/* 状态图标 */}
        {renderStatusIcon()}
      </button>

      {/* 内容区 */}
      {isExpanded && hasContent && (
        <div className="px-4 pb-4 pl-16">
          <div className="border-t border-gray-100 pt-3">
            {content}
          </div>
        </div>
      )}
    </div>
  );
};

interface Props {
  message: AssistantMessageType;
}

/** 助手消息组件 */
const AssistantMessage = ({ message }: Props) => {
  const { steps, status, error } = message;

  // 判断是否有任何步骤在进行中
  const hasActiveStep = steps.some(
    (record) => record.status === "running" || record.status === "streaming"
  );

  // 判断最后一个步骤是否为 execute 且已完成
  const lastStep = steps[steps.length - 1];
  const isExecuteDone = lastStep?.step === "execute" && lastStep?.status === "done";

  // 全局错误（会话级/系统级错误，无步骤记录）
  if (status === "error" && error && steps.length === 0) {
    return (
      <div className="rounded-lg bg-red-50 border border-red-200 p-4">
        <div className="flex items-center gap-2 text-red-700">
          <XCircle className="w-5 h-5" />
          <span className="font-medium">处理失败</span>
        </div>
        <p className="mt-2 text-sm text-red-600">{error}</p>
      </div>
    );
  }

  // 待处理状态（尚未开始任何步骤）
  if (status === "pending" && steps.length === 0) {
    return (
      <div className="rounded-lg bg-gray-50 border border-gray-200 p-4">
        <div className="flex items-center gap-3">
          <div className="flex items-center justify-center w-10 h-10 rounded-full bg-emerald-100">
            <Sparkles className="w-5 h-5 text-emerald-600" />
          </div>
          <div>
            <p className="text-sm font-medium text-gray-700">准备处理...</p>
            <p className="text-xs text-gray-500">正在建立连接</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* 渲染步骤列表 - 直接遍历 steps 数组 */}
      {steps.map((record, index) => (
        <StepItem
          key={`${record.step}-${index}`}
          record={record}
          defaultExpanded={record.step === "execute" || record.step === "export"}
        />
      ))}

      {/* 全局错误提示 */}
      {status === "error" && error && (
        <div className="rounded-lg bg-red-50 border border-red-200 p-3">
          <div className="flex items-center gap-2 text-red-700">
            <XCircle className="w-4 h-4" />
            <span className="text-sm">{error}</span>
          </div>
        </div>
      )}

      {/* 完成提示 */}
      {status === "done" && !hasActiveStep && isExecuteDone && (
        <div className="rounded-lg bg-emerald-50 border border-emerald-200 p-3">
          <div className="flex items-center gap-2 text-emerald-700">
            <CheckCircle2 className="w-4 h-4" />
            <span className="text-sm font-medium">处理完成</span>
          </div>
        </div>
      )}
    </div>
  );
};

export default AssistantMessage;
