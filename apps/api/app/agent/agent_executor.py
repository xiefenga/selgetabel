"""AgentExecutor — Agent 执行引擎（Phase 1 简化版 + Phase 4 完整版）"""

import asyncio
import logging
from typing import Any, AsyncGenerator, Optional

from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from app.agent.callbacks.sse import SSEAgentCallback, SSEEventQueue
from app.agent.memory.db_buffer import DBConversationBufferMemory
from app.agent.streaming import StreamEvent
from app.agent.tools.registry import ExcelToolRegistry

logger = logging.getLogger(__name__)


class AgentExecutor:
    """
    Agent 执行引擎。

    Phase 1/2: run_simple() / execute_tool() 直接工具调度
    Phase 4+: run() 基于 langchain.agents.create_agent 完整实现
    """

    def __init__(
        self,
        agent: Any,
        memory: DBConversationBufferMemory,
        tool_registry: ExcelToolRegistry,
        event_queue: Optional[SSEEventQueue] = None,
    ):
        self.agent = agent
        self.memory = memory
        self.tool_registry = tool_registry
        self._event_queue = event_queue or SSEEventQueue()
        self._abort_event = asyncio.Event()

    def set_abort(self) -> None:
        """SSE 连接断开时调用，中止当前运行中的 Agent"""
        self._abort_event.set()

    async def _load_file_collection(
        self,
        file_ids: list[str],
        user_id: str,
        db: Any,
    ):
        """
        Per-turn 预加载：从 file_ids 加载 FileCollection。

        这样做的好处：
        1. 所有工具共享同一 FileCollection 实例，修改相互可见
        2. 避免每个工具独立从 MinIO 读取（减少 IO）
        3. LLM 不需要传递 file_collection 参数（工具从 context 取）
        """
        from uuid import UUID
        from sqlalchemy import select
        from app.models.file import File
        from app.engine.excel_parser import ExcelParser

        try:
            file_uuid_list = [UUID(fid) for fid in file_ids]
            stmt = select(File).where(
                File.id.in_(file_uuid_list),
                File.user_id == UUID(user_id),
            )
            result = await db.execute(stmt)
            files = list(result.scalars().all())

            if not files:
                logger.warning(f"_load_file_collection: 未找到文件 {file_ids}")
                return None

            file_records = []
            for f in files:
                file_records.append((str(f.id), f.file_path, f.filename or "unknown.xlsx"))

            fc = ExcelParser.load_tables_from_minio_paths(file_records)
            logger.info(f"FileCollection 已预加载: {len(files)} 个文件")
            return fc
        except Exception as e:
            logger.exception(f"预加载 FileCollection 失败: {e}")
            return None

    # ─────────────────────────────────────────────────────────────
    # Phase 4: 完整 ConversableAgent 实现
    # ─────────────────────────────────────────────────────────────

    async def run(
        self,
        query: str,
        file_ids: list[str],
        model: BaseChatModel,
        system_prompt: str,
        user_id: str = "",
        db: Any = None,
    ) -> AsyncGenerator[StreamEvent, None]:
        """
        Phase 4 完整实现：使用 langchain.agents.create_agent 运行 Agent，
        事件通过 SSEEventQueue 异步传回。
        """
        self._abort_event.clear()
        tools = self.tool_registry.get_tools()

        # ── Per-turn 共享状态：预加载 FileCollection ──────────────────
        # 若有 file_ids，提前加载 FileCollection 并注入到工具 context
        file_collection = None
        if file_ids and db and user_id:
            file_collection = await self._load_file_collection(file_ids, user_id, db)

        # 更新工具 context（user_id/db 已由 ExcelAgent.__init__ 注入，这里只补充 file_collection）
        self.tool_registry.set_context(
            user_id=user_id,
            db=db,
            file_collection=file_collection,
        )

        try:
            agent = create_agent(
                model=model,
                tools=tools,
                system_prompt=system_prompt,
            )
        except Exception as e:
            logger.exception("create_agent 失败")
            yield StreamEvent(event="error", data={"message": f"Agent 创建失败: {e}"})
            yield StreamEvent(event="complete", data={"status": "error"})
            return

        # 从 DB memory 加载历史消息
        await self.memory._load_from_db_async()
        historical_messages = list(self.memory._memory.messages)

        # 构建初始输入：历史 + 当前查询
        # 若有 file_ids，通知 LLM 已预加载（解决"上传了文件但 LLM 看不见"的问题）
        from langchain_core.messages import SystemMessage
        file_ids = file_ids or []
        system_parts = []
        if file_ids:
            if file_collection:
                # 已预加载，告知 LLM 直接用工具操作，无需再读文件
                system_parts.append(
                    f"【重要】当前对话已上传 {len(file_ids)} 个文件。"
                    "文件已加载到内存，你可以直接调用 filter/sort/drop_columns 等工具操作数据。"
                    "read_excel 工具返回的是文件结构信息（列名等），不是数据本身。"
                )
            else:
                system_parts.append(
                    f"【重要】当前对话已上传 {len(file_ids)} 个文件，file_ids: {file_ids}。"
                    "在执行任何数据操作之前，你必须先调用 read_excel 工具读取文件，获得真实的列名和数据样本。"
                    "不要询问用户是否上传了文件，直接调用 read_excel。"
                )
        if historical_messages:
            system_parts.append(
                "以下是我们之前的对话历史，你可以引用其中的信息。"
            )

        input_messages: list = []
        if system_parts:
            input_messages.append(SystemMessage(content="\n".join(system_parts)))
        input_messages.extend(historical_messages)
        input_messages.append(HumanMessage(content=query))

        # SSE callback
        sse_callback = SSEAgentCallback(self._event_queue)

        # 创建 async task 在后台运行 agent.astream()
        agent_task: Optional[asyncio.Task] = None
        queue_task: Optional[asyncio.Task] = None

        async def consume_agent():
            """异步消耗 agent.astream()，将事件推入队列"""
            from langchain_core.messages import AIMessage, ToolMessage

            try:
                config: RunnableConfig = {"callbacks": [sse_callback]}

                async for state_event in agent.astream(
                    {"messages": input_messages},
                    config,
                ):
                    if self._abort_event.is_set():
                        logger.info("Agent 执行已中止（SSE 连接断开）")
                        break

                    # langgraph astream (stream_mode="updates") yields dicts like:
                    # {"model": {"messages": [...]}, ...}
                    # Each node's updated state is under its name key
                    model_state = state_event.get("model", {})
                    messages = model_state.get("messages", [])

                    # 遍历所有消息，处理工具调用和结果
                    for msg in messages:

                        # LLM 决定调用工具
                        if isinstance(msg, AIMessage) and msg.tool_calls:
                            for tool_call in msg.tool_calls:
                                # 获取工具名和参数（兼容不同结构）
                                if isinstance(tool_call, dict):
                                    tool_name = tool_call.get("name") or tool_call.get("id", "unknown")
                                    tool_args = tool_call.get("args", {})
                                else:
                                    # object形式 (BaseToolCall)
                                    tool_name = getattr(tool_call, "name", "unknown") or "unknown"
                                    tool_args = getattr(tool_call, "args", {})

                                await self._event_queue.put(StreamEvent(
                                    event="tool_start",
                                    data={"tool": tool_name, "args": tool_args}
                                ))

                                # 同时记录到 memory（供 save() 时持久化）
                                self.memory._memory.messages.append(msg)

                        # 工具执行结果
                        elif isinstance(msg, ToolMessage):
                            tool_name = msg.name or "unknown"
                            observation = msg.content or ""

                            # 流式发射结果
                            for i, char in enumerate(observation):
                                if self._abort_event.is_set():
                                    break
                                await self._event_queue.put(StreamEvent(
                                    event="tool_stream",
                                    data={"tool": tool_name, "delta": char, "partial": observation[:i+1]}
                                ))
                                await asyncio.sleep(0.01)

                            await self._event_queue.put(StreamEvent(
                                event="tool_end",
                                data={"tool": tool_name, "observation": observation}
                            ))

                            # 同时记录到 memory（存 dict，不存 ToolMessage 对象）
                            self.memory._memory.messages.append(msg.model_dump())

                    # 最终回复（无工具调用，有内容）
                    if messages:
                        last_msg = messages[-1]
                        if isinstance(last_msg, AIMessage) and last_msg.content and not last_msg.tool_calls:
                            content = last_msg.content

                            # 通知前端开始（工具名用 "chat"，会被当作纯文本渲染）
                            await self._event_queue.put(StreamEvent(
                                event="tool_start",
                                data={"tool": "chat", "args": {}}
                            ))

                            # 流式发送内容（按 chunk 而非逐字发送，减少 SSE 开销并让前端有渲染间隔）
                            chunk_size = 10
                            delay_per_chunk = 0.05  # 50ms per chunk
                            for start in range(0, len(content), chunk_size):
                                if self._abort_event.is_set():
                                    break
                                chunk = content[start:start + chunk_size]
                                partial = content[:start + chunk_size]
                                await self._event_queue.put(StreamEvent(
                                    event="tool_stream",
                                    data={"tool": "chat", "delta": chunk, "partial": partial}
                                ))
                                if start + chunk_size < len(content):
                                    await asyncio.sleep(delay_per_chunk)

                            # 通知前端工具结束
                            await self._event_queue.put(StreamEvent(
                                event="tool_end",
                                data={"tool": "chat", "observation": content}
                            ))

                            await self._event_queue.put(StreamEvent(
                                event="agent_end",
                                data={"response": content}
                            ))

                            # 同时记录到 memory
                            self.memory._memory.messages.append(last_msg)
            except asyncio.CancelledError:
                logger.info("Agent 任务被取消")
            except Exception as e:
                if not self._abort_event.is_set():
                    logger.exception(f"Agent 执行异常: {e}")
                    await self._event_queue.put(StreamEvent(
                        event="error",
                        data={"message": str(e)}
                    ))
            finally:
                self._event_queue.send_end_marker()

        # 启动 agent 后台任务
        agent_task = asyncio.create_task(consume_agent())

        # 从队列 yield 事件，同时支持 Abort
        while True:
            try:
                event = await asyncio.wait_for(
                    self._event_queue.get(),
                    timeout=1.0
                )
            except asyncio.TimeoutError:
                if self._abort_event.is_set():
                    if agent_task:
                        agent_task.cancel()
                    logger.info("Agent 执行已中止（队列超时）")
                    break
                continue

            if event is None:
                break

            yield event

        # 确保 agent 任务结束
        if agent_task and not agent_task.done():
            agent_task.cancel()
            try:
                await agent_task
            except asyncio.CancelledError:
                pass

        yield StreamEvent(event="complete", data={"status": "done"})

    # ─────────────────────────────────────────────────────────────
    # Phase 1/2: 简化直接工具调度
    # ─────────────────────────────────────────────────────────────

    async def run_simple(
        self,
        query: str,
        file_ids: list[str],
    ) -> AsyncGenerator[StreamEvent, None]:
        """
        Phase 1 直接工具调度（SSE 流式）。
        - 有文件但无明确意图 → ClarifyTool
        - 无文件或闲聊 → HelloTool
        """
        query_lower = query.strip().lower()

        use_hello = (
            not file_ids
            and any(kw in query_lower for kw in ["你好", "hi", "hello", "嗨", "帮助", "介绍", "谢谢"])
        )

        tool = self.tool_registry.get_tool("clarify" if file_ids and not use_hello else "hello")

        if tool is None:
            yield StreamEvent(event="error", data={"message": f"Tool not found"})
            yield StreamEvent(event="complete", data={"status": "error"})
            return

        yield StreamEvent(event="tool_start", data={"tool": tool.name, "args": {"query": query}})

        if tool.name == "hello":
            greeting = "你好！我是 Excel 智能助手，可以帮你处理数据分析、排序、筛选等操作。有什么我可以帮你的吗？"
        else:
            greeting = "您好！请告诉我您想对数据做什么操作，例如：分析这份数据的趋势、按照某列排序、筛选特定条件的记录等。"

        for i, char in enumerate(greeting):
            yield StreamEvent(
                event="tool_stream",
                data={"tool": tool.name, "delta": char, "partial": greeting[:i+1]}
            )
            await asyncio.sleep(0.015)

        yield StreamEvent(
            event="tool_end",
            data={"tool": tool.name, "observation": greeting, "data": {"success": True}}
        )
        yield StreamEvent(event="agent_end", data={"response": greeting})
        yield StreamEvent(event="complete", data={"status": "done"})

    async def execute_tool(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        file_collection: Any = None,
    ) -> AsyncGenerator[StreamEvent, None]:
        """
        Phase 2 工具调用入口。
        """
        tool = self.tool_registry.get_tool(tool_name)

        if tool is None:
            yield StreamEvent(event="error", data={"message": f"未知工具: {tool_name}"})
            yield StreamEvent(event="complete", data={"status": "error"})
            return

        if file_collection is not None and "file_collection" in tool_args:
            tool_args["file_collection"] = file_collection

        yield StreamEvent(event="tool_start", data={"tool": tool_name, "args": tool_args})

        try:
            result = await tool.arun(**tool_args)

            # arun() 返回 ToolMessage（langgraph 兼容格式）
            observation = result.content or ""

            if observation:
                for i, char in enumerate(observation):
                    yield StreamEvent(
                        event="tool_stream",
                        data={"tool": tool_name, "delta": char, "partial": observation[:i+1]}
                    )
                    await asyncio.sleep(0.01)

            yield StreamEvent(
                event="tool_end",
                data={
                    "tool": tool_name,
                    "observation": observation,
                }
            )

        except Exception as e:
            logger.exception(f"工具 {tool_name} 执行失败")
            yield StreamEvent(
                event="error",
                data={"tool": tool_name, "message": str(e)}
            )

        yield StreamEvent(event="complete", data={"status": "done" if tool else "error"})
