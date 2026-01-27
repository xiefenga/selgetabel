import axios from "axios";
import { events } from "fetch-event-stream";

import { API_BASE } from "~/lib/config";

import type { AxiosProgressEvent } from 'axios'


export interface UploadItem {
  id: string;
  path: string;
  filename: string;
  content_type: string | null
}

export type UploadResponse = UploadItem[];

export interface ApiResponse<T> {
  code: number;
  data: T | null;
  msg: string;
}

export interface SSEMessage {
  action: "load" | "analysis" | "generate" | "execute";
  status: "start" | "done" | "error";
  data?: {
    schemas?: Record<string, Record<string, string>>;
    content?: string | Record<string, unknown>;
    message?: string;
    output_file?: string;
    formulas?: string;
    turn_id?: string;
    thread_id?: string;
  };
}

export async function uploadFiles(files: File[], onProgress?: (progress: number) => void): Promise<UploadResponse> {
  const formData = new FormData();
  files.forEach((file) => formData.append("files", file));

  try {
    const res = await axios.post<ApiResponse<UploadResponse>>(`${API_BASE}/file/upload`, formData, {
      headers: {
        "Content-Type": "multipart/form-data",
      },
      onUploadProgress: (progressEvent: AxiosProgressEvent) => {
        if (progressEvent.total && onProgress) {
          const progress = Math.round((progressEvent.loaded * 100) / progressEvent.total);
          onProgress(progress);
        }
      },
    });

    const response = res.data;
    if (response.code !== 0) {
      throw new Error(response.msg || "上传失败");
    }

    if (!response.data) {
      throw new Error("响应数据为空");
    }

    return response.data;
  } catch (error) {
    if (axios.isAxiosError(error)) {
      // 尝试从统一响应格式中提取错误信息
      const responseData = error.response?.data;
      if (responseData && typeof responseData === 'object' && 'msg' in responseData) {
        throw new Error(responseData.msg as string);
      }
      // 兼容旧的错误格式
      const errorMessage = error.response?.data?.detail || error.response?.data?.msg || error.message || "上传失败";
      throw new Error(errorMessage);
    }
    throw new Error("上传失败");
  }
}

// 线程相关类型
export interface ThreadListItem {
  id: string;
  title: string | null;
  status: string;
  created_at: string;
  updated_at: string;
  turn_count: number;
}

export interface ThreadTurn {
  id: string;
  turn_number: number;
  user_query: string;
  status: string;
  analysis?: string | null;
  operations_json?: Record<string, unknown> | null;
  error_message?: string | null;
  created_at: string;
  completed_at?: string | null;
  file_ids?: string[];
  files?: { id: string, filename: string, path: string }[]
  result?: {
    output_file?: string | null;
    output_file_path?: string | null;
    formulas?: Record<string, unknown> | null;
  };
}

export interface ThreadDetail {
  id: string;
  title: string | null;
  status: string;
  created_at: string;
  updated_at: string;
  turns: ThreadTurn[];
}

// 获取线程列表
export async function getThreads(): Promise<ThreadListItem[]> {
  try {
    const res = await axios.get<ApiResponse<ThreadListItem[]>>(`${API_BASE}/threads`);
    if (res.data.code !== 0) {
      throw new Error(res.data.msg || "获取失败");
    }
    return res.data.data || [];
  } catch (error) {
    if (axios.isAxiosError(error)) {
      const errorMessage = error.response?.data?.msg || error.response?.data?.detail || error.message || "获取失败";
      throw new Error(errorMessage);
    }
    throw new Error("获取失败");
  }
}

// 获取线程详情
export async function getThreadDetail(threadId: string): Promise<ThreadDetail> {
  try {
    const res = await axios.get<ApiResponse<ThreadDetail>>(`${API_BASE}/threads/${threadId}`);
    if (res.data.code !== 0) {
      throw new Error(res.data.msg || "获取失败");
    }
    if (!res.data.data) {
      throw new Error("线程不存在");
    }
    return res.data.data;
  } catch (error) {
    if (axios.isAxiosError(error)) {
      const errorMessage = error.response?.data?.msg || error.response?.data?.detail || error.message || "获取失败";
      throw new Error(errorMessage);
    }
    throw new Error("获取失败");
  }
}

// 删除线程
export async function deleteThread(threadId: string): Promise<void> {
  try {
    const res = await axios.delete<ApiResponse<null>>(`${API_BASE}/threads/${threadId}`);
    if (res.data.code !== 0) {
      throw new Error(res.data.msg || "删除失败");
    }
  } catch (error) {
    if (axios.isAxiosError(error)) {
      const errorMessage = error.response?.data?.msg || error.response?.data?.detail || error.message || "删除失败";
      throw new Error(errorMessage);
    }
    throw new Error("删除失败");
  }
}

interface ProcessExcelOptions {
  body: {
    query: string;
    file_ids: string[];
    thread_id?: string;
  }
  events: {
    onStart?: () => void;
    onMessage?: (msg: SSEMessage) => void;
    onError?: (error: Error) => void;
    onSuccess?: () => void;
    onFinally?: () => void;
  }
}

interface ProcessPromise extends Promise<void> {
  abort: () => void;
}


export const processExcel = ({ body, events: { onStart, onMessage, onError, onSuccess, onFinally } }: ProcessExcelOptions) => {
  const controller = new AbortController();

  const trigger = async () => {
    try {
      const res = await fetch(`${API_BASE}/excel/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: controller.signal,
      });

      onStart?.();

      if (!res.ok) {
        throw new Error("请求失败");
      }

      for await (const event of events(res, controller.signal)) {
        if (!event.data) {
          continue;
        }
        try {
          const data = JSON.parse(event.data);
          onMessage?.(data as SSEMessage);
        } catch {
          // ignore parse errors
        }
      }
      onSuccess?.();
    } catch (err) {
      const error = err as Error;
      if (error.name !== "AbortError") {
        onError?.(error);
      }
    } finally {
      onFinally?.();
    }
  }

  const process: ProcessPromise = trigger() as ProcessPromise;

  process.abort = () => controller.abort();

  return process;
}

