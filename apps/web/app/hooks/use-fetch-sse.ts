import React from 'react'

interface Options {
  api: string
}

export const useFetchSSE = ({ api }: Options) => {
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
