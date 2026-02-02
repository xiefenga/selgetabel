// ========== 用户消息类型 ==========
export interface UserMessageAttachment {
  id: string
  filename: string
  path: string
}

export interface UserMessage {
  id: string;
  role: "user";
  content: string;
  files?: UserMessageAttachment[]
  created: number
  avatar: string
}

// ========== Step 类型定义（对齐 SSE_SPEC 和 STEPS_STORAGE_SPEC）==========

/** 步骤名称 */
export type StepName = "load" | "generate" | "validate" | "execute" | "export";

/** 步骤状态 */
export type StepStatus = "running" | "streaming" | "done" | "error";

/** 错误信息 */
export interface StepError {
  code: string;
  message: string;
}

// ========== 各步骤的 Output 类型 ==========

/** 文件列信息 */
export interface FileColumnInfo {
  name: string;
  letter: string;
  type: "text" | "number" | "date" | "boolean";
}

/** 文件 Sheet 信息 */
export interface FileSheetInfo {
  name: string;
  row_count: number;
  columns: FileColumnInfo[];
}

/** 文件信息 */
export interface FileInfo {
  file_id: string;
  filename: string;
  sheets: FileSheetInfo[];
}

/** load 步骤输出 */
export interface LoadStepOutput {
  files: FileInfo[];
}

/** generate 步骤输出 */
export interface GenerateStepOutput {
  operations: unknown[];
}

/** validate 步骤输出 */
export interface ValidateStepOutput {
  valid: boolean;
}

/** execute 步骤输出 */
export interface ExecuteStepOutput {
  strategy?: string;        // 思路解读
  manual_steps?: string;    // 快捷复现
  variables?: Record<string, unknown>;
  new_columns?: Record<string, unknown>;
  updated_columns?: Record<string, unknown>;
  new_sheets?: Record<string, unknown>;
  errors?: unknown[];
}

/** 输出文件信息 */
export interface OutputFileInfo {
  file_id: string;
  filename: string;
  url: string;
}

/** export 步骤输出 */
export interface ExportStepOutput {
  output_files: OutputFileInfo[];
}

/** 步骤 Output 类型映射 */
export type StepOutputMap = {
  load: LoadStepOutput;
  generate: GenerateStepOutput;
  validate: ValidateStepOutput;
  execute: ExecuteStepOutput;
  export: ExportStepOutput;
};

// ========== Step 记录类型（存储格式）==========

/** 基础步骤记录 */
interface BaseStepRecord<T extends StepName> {
  step: T;
  started_at?: string;
  completed_at?: string;
}

/** 运行中的步骤 */
export interface RunningStepRecord<T extends StepName = StepName> extends BaseStepRecord<T> {
  status: "running";
}

/** 流式输出中的步骤（仅用于实时显示，不持久化）*/
export interface StreamingStepRecord<T extends StepName = StepName> extends BaseStepRecord<T> {
  status: "streaming";
  /** 累积的流式内容（前端维护）*/
  streamContent?: string;
}

/** 完成的步骤 */
export interface DoneStepRecord<T extends StepName = StepName> extends BaseStepRecord<T> {
  status: "done";
  output: StepOutputMap[T];
}

/** 失败的步骤 */
export interface ErrorStepRecord<T extends StepName = StepName> extends BaseStepRecord<T> {
  status: "error";
  error: StepError;
}

/** 步骤记录联合类型 */
export type StepRecord<T extends StepName = StepName> =
  | RunningStepRecord<T>
  | StreamingStepRecord<T>
  | DoneStepRecord<T>
  | ErrorStepRecord<T>;

// ========== SSE 消息类型 ==========

/** Session 事件数据 */
export interface SessionEventData {
  thread_id: string;
  turn_id: string;
  title?: string;
  is_new_thread: boolean;
}

/** 步骤事件数据（默认 message 事件）*/
export interface StepEventData {
  step: StepName | "complete";
  status: StepStatus;
  delta?: string;
  output?: StepOutputMap[StepName] | { thread_id: string; turn_id: string };
  error?: StepError;
}

/** 错误事件数据 */
export interface ErrorEventData {
  code: string;
  message: string;
}

// ========== 助手消息类型 ==========

/** 助手消息状态 */
export type AssistantMessageStatus = "pending" | "streaming" | "done" | "error";

/** 助手消息 */
export interface AssistantMessage {
  id: string;
  role: "assistant";
  /** 消息状态 */
  status: AssistantMessageStatus;
  /** 步骤列表（核心数据）*/
  steps: StepRecord[];
  /** 全局错误信息（会话级/系统级错误）*/
  error?: string;
  /** 完成时间戳 */
  completed?: number;
}

// ========== 消息联合类型 ==========
export type Message = UserMessage | AssistantMessage;

// ========== 工具函数类型 ==========

/** 有效的步骤名称列表 */
const VALID_STEP_NAMES: StepName[] = ["load", "generate", "validate", "execute", "export"];

/** 获取每个步骤的最终状态 */
export function getLatestSteps(steps: StepRecord[]): Partial<Record<StepName, StepRecord>> {
  return steps.reduce(
    (acc, step) => {
      const stepName = step.step as string;
      if (VALID_STEP_NAMES.includes(stepName as StepName)) {
        acc[stepName as StepName] = step;
      }
      return acc;
    },
    {} as Partial<Record<StepName, StepRecord>>,
  );
}

/** 获取指定步骤的最终记录（类型安全）*/
export function getStepRecord<T extends StepName>(
  steps: StepRecord[],
  stepName: T
): StepRecord<T> | undefined {
  const records = steps.filter(s => s.step === stepName);
  return records[records.length - 1] as StepRecord<T> | undefined;
}

/** 判断步骤是否完成 */
export function isStepDone<T extends StepName>(
  record: StepRecord<T> | undefined
): record is DoneStepRecord<T> {
  return record?.status === "done";
}

/** 判断步骤是否有错误 */
export function isStepError<T extends StepName>(
  record: StepRecord<T> | undefined
): record is ErrorStepRecord<T> {
  return record?.status === "error";
}

/** 判断步骤是否正在流式输出 */
export function isStepStreaming<T extends StepName>(
  record: StepRecord<T> | undefined
): record is StreamingStepRecord<T> {
  return record?.status === "streaming";
}
