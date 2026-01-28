import { useState, useMemo } from "react";
import {
  ChevronRight,
  Loader2,
  CheckCircle2,
  XCircle,
  FileSpreadsheet,
  Brain,
  Code2,
  Play,
  Sparkles
} from "lucide-react";
import { cn } from "~/lib/utils";
import type {
  AssistantMessage as AssistantMessageType,
  StepRecord,
  StepName,
  DoneStepRecord,
  StreamingStepRecord,
  LoadStepOutput,
  AnalyzeStepOutput,
  GenerateStepOutput,
  ExecuteStepOutput,
} from "../types";

interface Props {
  message: AssistantMessageType;
}

/** 步骤配置 */
const STEP_CONFIG: Record<StepName, { label: string; icon: React.ReactNode }> = {
  load: {
    label: "加载文件",
    icon: <FileSpreadsheet className="w-4 h-4" />,
  },
  analyze: {
    label: "分析需求",
    icon: <Brain className="w-4 h-4" />,
  },
  generate: {
    label: "生成操作",
    icon: <Code2 className="w-4 h-4" />,
  },
  execute: {
    label: "执行处理",
    icon: <Play className="w-4 h-4" />,
  },
};

/** 步骤顺序 */
const STEP_ORDER: StepName[] = ["load", "analyze", "generate", "execute"];

/** 获取每个步骤的最终状态 */
function getLatestStepsMap(steps: StepRecord[]): Partial<Record<StepName, StepRecord>> {
  return steps.reduce(
    (acc, step) => {
      const stepName = step.step as string;
      if (STEP_ORDER.includes(stepName as StepName)) {
        acc[stepName as StepName] = step;
      }
      return acc;
    },
    {} as Partial<Record<StepName, StepRecord>>,
  );
}

/** 单个步骤项组件 */
interface StepItemProps {
  stepName: StepName;
  record?: StepRecord;
  defaultExpanded?: boolean;
}

const StepItem = ({ stepName, record, defaultExpanded = false }: StepItemProps) => {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);
  const config = STEP_CONFIG[stepName];

  // 步骤状态
  const status = record?.status;
  const isRunning = status === "running";
  const isStreaming = status === "streaming";
  const isDone = status === "done";
  const isError = status === "error";
  const isPending = !record;

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

  // 获取内容
  const getContent = () => {
    if (isStreaming) {
      const streamRecord = record as StreamingStepRecord;
      return streamRecord.streamContent || "";
    }
    if (isDone) {
      const doneRecord = record as DoneStepRecord;
      if (stepName === "load") {
        const output = doneRecord.output as LoadStepOutput;
        const schemas = output?.schemas || {};
        const tableNames = Object.keys(schemas);
        return (
          <div className="space-y-2">
            <p className="text-sm text-gray-600">
              已加载 {tableNames.length} 个表格
            </p>
            {tableNames.map((tableName) => {
              const columns = schemas[tableName] || {};
              const columnNames = Object.values(columns);
              return (
                <div key={tableName} className="bg-gray-50 rounded-lg p-3">
                  <p className="font-medium text-sm text-gray-800 mb-1">
                    {tableName}
                  </p>
                  <p className="text-xs text-gray-500 line-clamp-2">
                    列：{columnNames.join("、")}
                  </p>
                </div>
              );
            })}
          </div>
        );
      }
      if (stepName === "analyze") {
        const output = doneRecord.output as AnalyzeStepOutput;
        return (
          <div className="prose prose-sm max-w-none text-gray-700 whitespace-pre-wrap">
            {output?.content || ""}
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
      if (stepName === "execute") {
        const output = doneRecord.output as ExecuteStepOutput;
        const { formulas, output_file } = output || {};
        return (
          <div className="space-y-3">
            {output_file && (
              <div className="flex items-center gap-2 text-emerald-700 bg-emerald-50 rounded-lg px-3 py-2">
                <FileSpreadsheet className="w-4 h-4" />
                <span className="text-sm font-medium">{output_file}</span>
              </div>
            )}
            {formulas && formulas.length > 0 && (
              <div>
                <p className="text-sm text-gray-600 mb-2">生成的公式：</p>
                <pre className="bg-gray-50 rounded-lg p-3 text-xs overflow-x-auto">
                  {JSON.stringify(formulas, null, 2)}
                </pre>
              </div>
            )}
          </div>
        );
      }
    }
    if (isError && record && "error" in record) {
      return (
        <div className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">
          {record.error?.message || "发生错误"}
        </div>
      );
    }
    return null;
  };

  const content = getContent();
  const hasContent = content !== null && content !== "";

  // 如果步骤还没开始，显示简化版
  if (isPending) {
    return (
      <div className="flex items-center gap-3 px-3 py-2 opacity-50">
        {renderStatusIcon()}
        <span className="text-sm text-gray-600">{config.icon}</span>
        <span className="text-sm text-gray-500">{config.label}</span>
      </div>
    );
  }

  return (
    <div className={cn(
      "border rounded-lg transition-all",
      isError ? "border-red-200 bg-red-50/50" : "border-gray-200 bg-white",
      isRunning || isStreaming ? "ring-2 ring-emerald-500/20" : ""
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
          (isRunning || isStreaming) && "bg-emerald-100 text-emerald-700",
          isPending && "bg-gray-100 text-gray-500"
        )}>
          {config.icon}
        </span>

        {/* 步骤名称 */}
        <span className={cn(
          "flex-1 text-sm font-medium",
          isDone && "text-gray-900",
          isError && "text-red-700",
          (isRunning || isStreaming) && "text-emerald-700",
          isPending && "text-gray-500"
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
            {typeof content === "string" ? (
              <div className="prose prose-sm max-w-none text-gray-700 whitespace-pre-wrap">
                {content}
                {isStreaming && (
                  <span className="inline-block w-2 h-4 bg-emerald-500 ml-0.5 animate-pulse" />
                )}
              </div>
            ) : (
              content
            )}
          </div>
        </div>
      )}
    </div>
  );
};

/** 助手消息组件 */
const AssistantMessage = ({ message }: Props) => {
  const { steps, status, error } = message;

  // 获取各步骤的最终状态
  const latestSteps = useMemo(() => getLatestStepsMap(steps), [steps]);

  // 判断是否有任何步骤在进行中
  const hasActiveStep = STEP_ORDER.some(stepName => {
    const record = latestSteps[stepName];
    return record?.status === "running" || record?.status === "streaming";
  });

  // 全局错误（会话级/系统级错误）
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

  // 待处理状态
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
      {/* 渲染步骤列表 */}
      {STEP_ORDER.map((stepName) => {
        const record = latestSteps[stepName];
        // 只显示已开始的步骤，或者正在流式处理时显示下一个步骤
        if (!record) return null;

        return (
          <StepItem
            key={stepName}
            stepName={stepName}
            record={record}
            // analyze 步骤默认展开（因为是主要内容）
            defaultExpanded={stepName === "analyze" || stepName === "execute"}
          />
        );
      })}

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
      {status === "done" && !hasActiveStep && latestSteps.execute?.status === "done" && (
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
