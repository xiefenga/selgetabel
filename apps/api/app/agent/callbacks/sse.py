"""Phase 4 SSE 回调处理器 — LangChain BaseCallbackHandler → SSE 事件"""

import asyncio
import logging
from typing import Any, Optional

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

from app.agent.streaming import StreamEvent

logger = logging.getLogger(__name__)


class SSEEventQueue:
    """
    线程安全的异步队列，用于将 LangChain 回调事件转为 SSE 事件。
    """

    def __init__(self):
        self._queue: asyncio.Queue[Optional[StreamEvent]] = asyncio.Queue()
        self._tool_output_buffers: dict[str, str] = {}

    async def put(self, event: StreamEvent) -> None:
        await self._queue.put(event)

    async def get(self) -> Optional[StreamEvent]:
        return await self._queue.get()

    def put_nowait(self, event: StreamEvent) -> None:
        self._queue.put_nowait(event)

    def buffer_append(self, tool_name: str, delta: str) -> None:
        if tool_name not in self._tool_output_buffers:
            self._tool_output_buffers[tool_name] = ""
        self._tool_output_buffers[tool_name] += delta

    def buffer_drain(self, tool_name: str) -> str:
        return self._tool_output_buffers.pop(tool_name, "")

    def send_end_marker(self) -> None:
        self._queue.put_nowait(None)


class SSEAgentCallback(BaseCallbackHandler):
    """
    LangChain BaseCallbackHandler → SSE 事件发射器。

    LangChain Core 1.x 的 BaseCallbackHandler 方法是同步的，
    因此使用 asyncio.get_event_loop().create_task() 将 SSE 事件
    异步发送到队列。
    """

    def __init__(self, queue: SSEEventQueue):
        self.queue = queue
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def _emit(self, coro) -> None:
        """在线程池中发射异步 SSE 事件（sync → async bridge）"""
        try:
            loop = asyncio.get_running_loop()
            loop.call_soon_threadsafe(lambda: asyncio.create_task(coro))
        except RuntimeError:
            # 无 running loop（如同步上下文），尝试获取或创建
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.call_soon(lambda: asyncio.create_task(coro))
                loop.run_until_complete(asyncio.sleep(0))
            except Exception as e:
                logger.warning(f"_emit failed: {e}")

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: Optional[str] = None,
        parent_run_id: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        tool_name = serialized.get("name", "unknown") if serialized else "unknown"
        coro = self.queue.put(StreamEvent(
            event="tool_start",
            data={"tool": tool_name, "args": input_str}
        ))
        self._emit(coro)
        self.queue.buffer_append(tool_name, "")

    def on_tool_end(
        self,
        output: str,
        *,
        run_id: Optional[str] = None,
        parent_run_id: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        tool_name = kwargs.get("serialized", {}).get("name", "unknown")
        final_content = self.queue.buffer_drain(tool_name) or output
        coro = self.queue.put(StreamEvent(
            event="tool_end",
            data={"tool": tool_name, "observation": final_content, "data": {"success": True}}
        ))
        self._emit(coro)

    def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: Optional[str] = None,
        parent_run_id: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        tool_name = kwargs.get("serialized", {}).get("name", "unknown")
        coro = self.queue.put(StreamEvent(
            event="tool_end",
            data={"tool": tool_name, "error": str(error), "data": {"success": False}}
        ))
        self._emit(coro)

    def on_text(
        self,
        text: str,
        *,
        run_id: Optional[str] = None,
        parent_run_id: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """LLM 推理过程中的文本输出（可选：作为 agent_thought 事件上报）"""
        pass

    def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        *,
        run_id: Optional[str] = None,
        parent_run_id: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        pass

    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: Optional[str] = None,
        parent_run_id: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        pass

    def on_chain_end(
        self,
        outputs: dict[str, Any],
        *,
        run_id: Optional[str] = None,
        parent_run_id: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        pass

    def on_agent_action(
        self,
        action: Any,
        *,
        run_id: Optional[str] = None,
        parent_run_id: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """Agent 决定调用工具时（LLM 决定）"""
        pass
