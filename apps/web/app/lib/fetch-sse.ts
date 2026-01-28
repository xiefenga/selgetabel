import { events } from "fetch-event-stream";
import { API_BASE } from "./config";



interface ProcessPromise extends Promise<void> {
  abort: () => void;
}

interface Params {
  url: string
  body: object
  events?: {
    onStart?: () => void;
    onMessage?: (event: string, msg: unknown) => void;
    onError?: (error: Error) => void;
    onSuccess?: () => void;
    onFinally?: () => void;
  }
}


export const fetchSSE = ({ url, body, events: _events = {} }: Params) => {
  const { onStart, onMessage, onError, onSuccess, onFinally } = _events

  const controller = new AbortController();

  const trigger = async () => {
    try {
      const res = await fetch(`${API_BASE}${url}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: controller.signal,
      });

      onStart?.();

      if (!res.ok) {
        throw new Error("请求失败");
      }

      for await (const { event = 'message', data: rawData } of events(res, controller.signal)) {
        if (rawData) {
          try {
            const data = JSON.parse(rawData);
            onMessage?.(event, data);
          } catch {
            // ignore parse errors
          }
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