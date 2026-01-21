import { Streamdown } from "streamdown";
import { Check, Loader2, X } from "lucide-react";

import { cn } from "~/lib/utils";

import type { AssistantMessage as AssistantMessageType } from "../types";

interface Props {
  message: AssistantMessageType;
}

const STEP_ORDER: Array<"loading" | "analyzing" | "generating" | "executing"> = [
  "loading",
  "analyzing",
  "generating",
  "executing",
];

const STEP_LABELS: Record<(typeof STEP_ORDER)[number], string> = {
  loading: "加载文件",
  analyzing: "分析需求",
  generating: "生成操作",
  executing: "执行操作",
};

const STEP_STATUS_TEXT: Record<"start" | "done" | "error", string> = {
  start: "进行中",
  done: "完成",
  error: "出错",
};

const AssistantMessage = ({ message }: Props) => {
  return (
    <div className="rounded-lg px-4 py-3 bg-white text-gray-900">
      <div className="space-y-4">
        {message.steps && (
          <div className="space-y-3">
            {STEP_ORDER.map((step) => {
              const status = message.steps?.[step];
              if (!status) return null;

              const isActive = status === "start";
              const isDone = status === "done";
              const isError = status === "error";

              return (
                <div key={step} className="flex items-start gap-2">
                  <div className="mt-0.5">
                    {isActive && <Loader2 className="w-4 h-4 text-amber-500 animate-spin" />}
                    {isDone && <Check className="w-4 h-4 text-emerald-600" />}
                    {isError && <X className="w-4 h-4 text-red-500" />}
                  </div>
                  <div className="flex-1 space-y-2 w-full">
                    <div className={cn(isError ? "text-red-500" : "text-gray-800")}>
                      {STEP_LABELS[step]}
                    </div>
                    {/* 在对应步骤位置内联放展开内容 */}
                    {isDone && step === "analyzing" && message.analysis && (
                      <details className="group overflow-hidden">
                        <summary className="cursor-pointer text-gray-600 hover:text-gray-900 text-sm">
                          📋 查看需求分析
                        </summary>
                        <div className="mt-1">
                          <Streamdown className="w-full text-sm">{message.analysis}</Streamdown>
                        </div>
                      </details>
                    )}

                    {isDone && step === "generating" && message.operations && (
                      <details className="group">
                        <summary className="cursor-pointer text-gray-600 hover:text-gray-900 text-sm">
                          ⚙️ 查看生成的操作
                        </summary>
                        <pre className="mt-2 p-2 bg-gray-50 rounded text-xs overflow-auto">
                          {JSON.stringify(message.operations, null, 2)}
                        </pre>
                      </details>
                    )}

                    {isDone && step === "executing" && (message.formulas || message.outputFile) && (
                      <details className="group">
                        <summary className="cursor-pointer text-gray-600 hover:text-gray-900 text-sm">
                          📝 查看执行结果/公式
                        </summary>
                        <div className="mt-2 space-y-2 text-xs text-gray-700">
                          {message.formulas && (
                            <pre className="p-2 bg-gray-50 rounded text-xs overflow-auto whitespace-pre-wrap">
                              {message.formulas}
                            </pre>
                          )}
                          {message.outputFile && (
                            <a
                              href={`/api/${message.outputFile}`}
                              className="inline-flex items-center gap-2 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded"
                            >
                              下载结果文件
                            </a>
                          )}
                        </div>
                      </details>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  )
}

export default AssistantMessage