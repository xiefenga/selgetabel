import { useEffect, useState, useRef, useCallback } from "react";
import { Link, useParams } from "react-router";
import { ChevronLeft, Play, Loader2, CheckCircle, XCircle, MessageSquare, FileSpreadsheet, Tag } from "lucide-react";

import { Button } from "~/components/ui/button";
import { runFixtureCase, getFixtureScenario } from "~/lib/api";
import type { FixtureSSEStep, FixtureSSEComplete, FixtureSSEError, FixtureCaseSummary, FixtureDataset } from "~/lib/api";

// Step 日志条目（合并 running/streaming/done）
interface StepLogEntry {
  id: number;
  type: "step";
  step: string;
  stageId: string;  // 阶段实例唯一标识（用于区分重试）
  status: "running" | "streaming" | "done" | "error";
  startedAt: Date;
  completedAt?: Date;
  streamingContent?: string;  // streaming 阶段累积的内容
  output?: unknown;           // done 阶段的输出
  error?: string;             // error 阶段的错误信息
}

// 其他日志条目
interface OtherLogEntry {
  id: number;
  type: "complete" | "error";
  timestamp: Date;
  data: FixtureSSEComplete | FixtureSSEError;
  raw: string;
}

type SSELogEntry = StepLogEntry | OtherLogEntry;

const FixtureCaseRunPage = () => {
  const { scenario: scenarioId, case: caseId } = useParams();

  const [isRunning, setIsRunning] = useState(false);
  const [hasStarted, setHasStarted] = useState(false);
  const [logs, setLogs] = useState<SSELogEntry[]>([]);
  const [result, setResult] = useState<FixtureSSEComplete | null>(null);
  const [caseInfo, setCaseInfo] = useState<FixtureCaseSummary | null>(null);
  const [datasets, setDatasets] = useState<FixtureDataset[]>([]);
  const [scenarioName, setScenarioName] = useState<string>("");
  const [loadingCase, setLoadingCase] = useState(true);

  const logIdRef = useRef(0);
  const logsEndRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<(() => void) | null>(null);
  // 跟踪每个 stage_id 对应的日志 ID，用于更新（使用 stage_id 可以区分重试）
  const stageIdLogMapRef = useRef<Record<string, number>>({});

  // 加载用例信息
  useEffect(() => {
    if (!scenarioId || !caseId) return;

    const fetchCase = async () => {
      try {
        setLoadingCase(true);
        const scenario = await getFixtureScenario(scenarioId);
        const foundCase = scenario.cases.find((c) => c.id === caseId);
        if (foundCase) {
          setCaseInfo(foundCase);
        }
        setDatasets(scenario.datasets || []);
        setScenarioName(scenario.name || "");
      } catch (err) {
        console.error("Failed to load case info:", err);
      } finally {
        setLoadingCase(false);
      }
    };
    fetchCase();
  }, [scenarioId, caseId]);

  // 自动滚动到底部
  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  // 添加非 step 类型的日志
  const addOtherLog = useCallback((type: "complete" | "error", data: FixtureSSEComplete | FixtureSSEError) => {
    const entry: OtherLogEntry = {
      id: ++logIdRef.current,
      type,
      timestamp: new Date(),
      data,
      raw: JSON.stringify(data, null, 2),
    };
    setLogs((prev) => [...prev, entry]);
  }, []);

  // 处理 step 事件（使用 stage_id 合并 running/streaming/done 为一条记录）
  const handleStepEvent = useCallback((data: FixtureSSEStep) => {
    const stageId = data.stage_id || `${data.step}-${Date.now()}`; // 兼容无 stage_id 的情况

    setLogs((prev) => {
      // 使用 stage_id 查找是否已有日志条目
      const existingLogId = stageIdLogMapRef.current[stageId];
      const existingIndex = prev.findIndex((log) => log.id === existingLogId);

      if (existingIndex >= 0) {
        // 更新已有条目
        const existingLog = prev[existingIndex] as StepLogEntry;
        const updatedLog: StepLogEntry = { ...existingLog };

        if (data.status === "streaming" && data.delta) {
          updatedLog.status = "streaming";
          updatedLog.streamingContent = (existingLog.streamingContent || "") + data.delta;
        } else if (data.status === "done") {
          updatedLog.status = "done";
          updatedLog.completedAt = new Date();
          updatedLog.output = data.output;
        } else if (data.status === "error") {
          updatedLog.status = "error";
          updatedLog.completedAt = new Date();
          updatedLog.error = data.error;
        }

        return [...prev.slice(0, existingIndex), updatedLog, ...prev.slice(existingIndex + 1)];
      } else {
        // 创建新条目（使用 stage_id 作为 key）
        const newId = ++logIdRef.current;
        stageIdLogMapRef.current[stageId] = newId;

        const newLog: StepLogEntry = {
          id: newId,
          type: "step",
          step: data.step,
          stageId: stageId,
          status: data.status === "streaming" ? "streaming" : data.status,
          startedAt: new Date(),
          streamingContent: data.status === "streaming" ? data.delta : undefined,
          output: data.status === "done" ? data.output : undefined,
          error: data.status === "error" ? data.error : undefined,
          completedAt: data.status === "done" || data.status === "error" ? new Date() : undefined,
        };

        return [...prev, newLog];
      }
    });
  }, []);

  // 开始运行测试
  const handleRun = useCallback(() => {
    if (!scenarioId || !caseId) return;

    setIsRunning(true);
    setHasStarted(true);
    setLogs([]);
    setResult(null);
    logIdRef.current = 0;
    stageIdLogMapRef.current = {};

    const process = runFixtureCase({
      scenarioId,
      caseId,
      events: {
        onMeta: () => {
          // meta 事件已废弃，忽略
        },
        onStep: handleStepEvent,
        onComplete: (data) => {
          setResult(data);
          addOtherLog("complete", data);
        },
        onError: (data) => {
          addOtherLog("error", data);
        },
        onFinally: () => {
          setIsRunning(false);
        },
      },
    });

    abortRef.current = process.abort;
  }, [scenarioId, caseId, addOtherLog, handleStepEvent]);

  // 停止运行
  const handleStop = useCallback(() => {
    abortRef.current?.();
    setIsRunning(false);
  }, []);

  // 组件卸载时停止
  useEffect(() => {
    return () => {
      abortRef.current?.();
    };
  }, []);

  return (
    <div className="h-screen flex flex-col overflow-hidden bg-linear-to-br from-gray-50 via-white to-emerald-50/30">
      {/* Header Area */}
      <div className="shrink-0 pt-6 pb-4 max-w-7xl mx-auto w-full">

        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-start gap-2">
            <Link to={`/fixtures/${scenarioId}`} className="p-1 hover:bg-gray-100 rounded-full cursor-pointer">
              <ChevronLeft className="w-6 h-6" />
            </Link>
            <div>
              <div className="flex items-center gap-2 mb-1">
                {scenarioName && (
                  <span className="text-sm text-gray-500">{scenarioName}</span>
                )}
                {scenarioName && <span className="text-gray-300">/</span>}
                <h1 className="text-xl font-bold text-gray-900">
                  {caseInfo?.name || '测试用例运行'}
                </h1>
              </div>
              <p className="text-gray-400 font-mono text-xs">
                {scenarioId} / {caseId}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {isRunning ? (
              <Button variant="destructive" onClick={handleStop}>
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                停止
              </Button>
            ) : (
              <Button onClick={handleRun} className="bg-emerald-600 hover:bg-emerald-700">
                <Play className="w-4 h-4 mr-2" />
                运行测试
              </Button>
            )}
          </div>
        </div>

        <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden p-3 mt-2">
          {/* Case Info */}
          {loadingCase && !caseInfo ? (
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-lg bg-emerald-100 flex items-center justify-center shrink-0">
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-gray-800 text-sm leading-relaxed whitespace-pre-wrap">
                  加载用例信息...
                </p>
              </div>
            </div>
          ) : caseInfo && (
            <div className="space-y-3">
              {/* Prompt */}
              <div className="flex items-start gap-2">
                <div className="w-7 h-7 rounded-lg bg-emerald-100 flex items-center justify-center shrink-0">
                  <MessageSquare className="w-3.5 h-3.5 text-emerald-600" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-gray-800 text-sm leading-relaxed whitespace-pre-wrap">
                    {caseInfo.prompt}
                  </p>
                </div>
              </div>

              {/* Tags */}
              {caseInfo.tags && caseInfo.tags.length > 0 && (
                <div className="flex items-start gap-2">
                  <div className="w-7 h-7 rounded-lg bg-gray-100 flex items-center justify-center shrink-0">
                    <Tag className="w-3.5 h-3.5 text-gray-500" />
                  </div>
                  <div className="flex-1 min-w-0 flex flex-wrap items-center gap-2">
                    {caseInfo.tags.map((tag) => (
                      <span
                        key={tag}
                        className="inline-flex items-center px-2 py-1 bg-gray-100 text-gray-600 text-xs font-medium rounded-md"
                      >
                        {tag}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Datasets */}
              {datasets.length > 0 && (
                <div className="flex items-start gap-2">
                  <div className="w-7 h-7 rounded-lg bg-blue-100 flex items-center justify-center shrink-0">
                    <FileSpreadsheet className="w-3.5 h-3.5 text-blue-600" />
                  </div>
                  <div className="flex-1 min-w-0 flex flex-wrap items-center gap-2">
                    {datasets.map((dataset) => (
                      <span
                        key={dataset.file}
                        className="inline-flex items-center gap-1.5 px-2 py-1 bg-blue-50 text-blue-700 text-xs font-medium rounded-md border border-blue-200"
                        title={dataset.description}
                      >
                        <FileSpreadsheet className="w-3 h-3" />
                        {dataset.file}
                      </span>
                    ))}
                  </div>
                </div>
              )}


            </div>
          )}
        </div>
      </div>

      {/* Main Content Area - Flex to fill remaining space */}
      <div className="flex-1 min-h-0 px-6 pb-6">
        <div className="max-w-7xl mx-auto h-full flex gap-6">
          {/* Left: SSE Logs - Takes remaining space */}
          <div className="flex-1 min-w-0 flex flex-col bg-gray-900 rounded-xl overflow-hidden shadow-lg">
            <div className="shrink-0 px-4 py-3 bg-gray-800 border-b border-gray-700 flex items-center justify-between">
              <span className="text-sm font-medium text-gray-300">执行流程</span>
              {isRunning && (
                <span className="flex items-center gap-2 text-sm text-emerald-400">
                  <span className="w-2 h-2 bg-emerald-400 rounded-full animate-pulse" />
                  接收中...
                </span>
              )}
              {/* Result Status */}
              {result && (
                <div className="flex items-center gap-3 text-sm">
                  {/* Result Header */}
                  <div className={`flex items-center gap-1 ${result.success ? "text-green-100/50" : "text-red-100/50"}`}>
                    {result.success ? (
                      <CheckCircle className="w-4 h-4 text-green-600" />
                    ) : (
                      <XCircle className="w-4 h-4 text-red-600" />
                    )}
                    <span className={`font-semibold ${result.success ? "text-green-700" : "text-red-700"}`}>
                      {result.success ? "测试通过" : "测试失败"}
                    </span>
                  </div>

                  {/* Result Body */}
                  {result.output_file && (
                    <a href={result.output_file} target="_blank" rel="noopener noreferrer" className="text-sm text-emerald-600 hover:underline">
                      下载结果文件
                    </a>
                  )}
                </div>
              )}

              {/* Empty State for Result */}
              {!result && hasStarted && !isRunning && (
                <div className="bg-gray-100 rounded-xl border border-gray-200 p-4 text-center text-gray-500 text-sm">
                  测试未完成
                </div>
              )}
            </div>
            <div className="flex-1 min-h-0 overflow-y-auto p-4 font-mono text-sm">
              {!hasStarted ? (
                <div className="flex items-center justify-center h-full text-gray-500">
                  点击「运行测试」按钮开始
                </div>
              ) : logs.length === 0 && isRunning ? (
                <div className="flex items-center justify-center h-full text-gray-500">
                  <Loader2 className="w-5 h-5 animate-spin mr-2" />
                  等待服务器响应...
                </div>
              ) : (
                <div className="space-y-3">
                  {logs.map((log) => (
                    <LogEntry key={log.id} log={log} />
                  ))}
                  <div ref={logsEndRef} />
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

interface LogEntryProps {
  log: SSELogEntry;
}

const LogEntry = ({ log }: LogEntryProps) => {
  // Step 类型的日志
  if (log.type === "step") {
    return <StepLogEntryView log={log} />;
  }

  // 其他类型的日志 (complete, error)
  const otherLog = log as OtherLogEntry;

  const getStyles = () => {
    switch (otherLog.type) {
      case "complete":
        const completeData = otherLog.data as FixtureSSEComplete;
        return completeData.success
          ? {
            badge: "bg-green-500/20 text-green-400 border-green-500/30",
            icon: <CheckCircle className="w-3.5 h-3.5" />,
          }
          : {
            badge: "bg-red-500/20 text-red-400 border-red-500/30",
            icon: <XCircle className="w-3.5 h-3.5" />,
          };
      case "error":
        return {
          badge: "bg-red-500/20 text-red-400 border-red-500/30",
          icon: <XCircle className="w-3.5 h-3.5" />,
        };
      default:
        return {
          badge: "bg-gray-500/20 text-gray-400 border-gray-500/30",
          icon: null,
        };
    }
  };

  const styles = getStyles();
  const time = otherLog.timestamp.toLocaleTimeString("zh-CN", {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    fractionalSecondDigits: 3,
  });

  return (
    <div className="group">
      <div className="flex items-start gap-3">
        <span className="text-gray-500 shrink-0">{time}</span>
        <span
          className={`inline-flex items-center gap-1.5 px-2 py-0.5 text-xs font-medium rounded border shrink-0 ${styles.badge}`}
        >
          {styles.icon}
          {otherLog.type}
        </span>
      </div>
      <pre className="mt-2 text-gray-300 whitespace-pre-wrap break-all bg-gray-800/50 rounded-lg p-3 overflow-x-auto">
        {otherLog.raw}
      </pre>
    </div>
  );
};

// Step 日志条目视图组件（合并 running/streaming/done）
const StepLogEntryView = ({ log }: { log: StepLogEntry }) => {
  const getStyles = () => {
    switch (log.status) {
      case "error":
        return {
          badge: "bg-red-500/20 text-red-400 border-red-500/30",
          icon: <XCircle className="w-3.5 h-3.5" />,
          contentClass: "text-red-300 bg-red-900/20",
        };
      case "done":
        return {
          badge: "bg-green-500/20 text-green-400 border-green-500/30",
          icon: <CheckCircle className="w-3.5 h-3.5" />,
          contentClass: "text-gray-300 bg-gray-800/50",
        };
      case "streaming":
        return {
          badge: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
          icon: <Loader2 className="w-3.5 h-3.5 animate-spin" />,
          contentClass: "text-emerald-300 bg-emerald-900/20",
        };
      default: // running
        return {
          badge: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
          icon: <Loader2 className="w-3.5 h-3.5 animate-spin" />,
          contentClass: "text-yellow-300 bg-yellow-900/20",
        };
    }
  };

  const styles = getStyles();
  const time = log.startedAt.toLocaleTimeString("zh-CN", {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    fractionalSecondDigits: 3,
  });

  // 计算耗时
  const getDuration = () => {
    if (!log.completedAt) return null;
    const ms = log.completedAt.getTime() - log.startedAt.getTime();
    if (ms < 1000) return `${ms}ms`;
    return `${(ms / 1000).toFixed(2)}s`;
  };

  // 获取显示内容
  const getContent = () => {
    if (log.status === "done" && log.output) {
      return JSON.stringify(log.output, null, 2);
    }
    if (log.status === "streaming" && log.streamingContent) {
      return log.streamingContent;
    }
    if (log.status === "error" && log.error) {
      return log.error;
    }
    return log.status === "running" ? "执行中..." : "";
  };

  const content = getContent();
  const duration = getDuration();

  return (
    <div className="group">
      <div className="flex items-center gap-3">
        <span className="text-gray-500 shrink-0">{time}</span>
        <span
          className={`inline-flex items-center gap-1.5 px-2 py-0.5 text-xs font-medium rounded border shrink-0 ${styles.badge}`}
        >
          {styles.icon}
          {log.step}
        </span>
        <span className="text-xs text-gray-500">
          {log.status}
          {log.status === "streaming" && log.streamingContent && (
            <span className="ml-1">({log.streamingContent.length} chars)</span>
          )}
          {duration && <span className="ml-1">({duration})</span>}
        </span>
      </div>
      {content && (
        <pre className={`mt-2 whitespace-pre-wrap break-all rounded-lg p-3 overflow-x-auto ${styles.contentClass}`}>
          {content}
        </pre>
      )}
    </div>
  );
};

export default FixtureCaseRunPage;
