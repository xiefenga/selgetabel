"""DB ↔ ConversationBufferMemory 互转"""

import logging
import asyncio
from typing import Optional
from uuid import UUID

from langchain_classic.memory import ConversationBufferMemory
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.memory.token_manager import TokenManager

logger = logging.getLogger(__name__)


class _ChatHistory:
    """轻量级聊天历史容器（用于替代 LangChain 内部 chat_history）"""

    def __init__(self, messages: Optional[list] = None):
        self.messages: list = messages or []


class LazyConversationBufferMemory(ConversationBufferMemory):
    """
    惰性 ConversationBufferMemory。

    - 首次访问 chat_memory 时，从 DB 加载历史（Phase 3 异步实现）
    - 每次 save() 时，先加载 DB 历史 → 合并新消息 → Token 截断 → 保存回 DB
    - _loaded 标志确保每个请求周期内只加载一次
    """

    # 线程本地 flag，避免同步 property 中重复调用 async load
    _loading_in_progress: set = set()

    def __init__(
        self,
        thread_id: UUID,
        user_id: UUID,
        db_session: AsyncSession,
        max_tokens: int = 16000,
        model_id: str = "default",
    ):
        super().__init__(return_messages=True, output_key="output", input_key="input")
        self._thread_id = thread_id
        self._user_id = user_id
        self._db = db_session
        self._max_tokens = max_tokens
        self._model_id = model_id
        self._loaded = False
        self._token_manager = TokenManager(model_id=model_id, max_tokens=max_tokens)
        # 内部消息列表（LangChain 会通过 chat_memory setter 追加消息）
        self._memory = _ChatHistory()

    @property
    def chat_memory(self) -> _ChatHistory:
        """
        惰性加载：首次访问时从 DB 读取。

        注意：由于 LangChain 的 chat_memory 是同步 @property，
        实际加载在 save() 开始时执行（async context 可用）。
        此 property 仅返回已加载的 _memory。
        """
        return self._memory

    def _load_from_db_sync(self) -> None:
        """
        同步版本的 DB 加载（内部使用 run_in_executor）。

        每个请求周期只执行一次（通过 _loaded 标志控制）。
        """
        if self._loaded:
            return

        # 避免并发重复加载
        key = str(self._thread_id)
        if key in self._loading_in_progress:
            return
        self._loading_in_progress.add(key)

        try:
            # 在线程池中运行 async load_messages_history
            loop = asyncio.get_event_loop()
            if loop.is_running():
                future = asyncio.ensure_future(
                    self._load_from_db_async()
                )
                # 同步等待（仅在有 running loop 时可用）
                loop.run_until_complete(future)
            else:
                # 极端情况：loop 未运行（不应该在 async context 外调用）
                pass
        finally:
            self._loading_in_progress.discard(key)
            self._loaded = True

    async def _load_from_db_async(self) -> None:
        """
        异步加载 DB 历史到 _memory.messages。

        Phase 3 真实实现：从 TurnRepository.load_messages_history() 读取，
        还原为 LangChain 消息对象。
        """
        from app.persistence.turn_repository import TurnRepository

        repo = TurnRepository(self._db)
        messages_data = await repo.load_messages_history(self._thread_id)

        self._memory.messages.clear()
        for msg_data in messages_data:
            role = msg_data.get("role", "")
            content = msg_data.get("content", "")
            if role == "user":
                self._memory.messages.append(HumanMessage(content=content))
            elif role == "tool":
                # 还原 ToolMessage
                tool_name = msg_data.get("name", "")
                self._memory.messages.append(ToolMessage(content=content, name=tool_name))
            elif role == "assistant":
                self._memory.messages.append(AIMessage(content=content))

        logger.debug(
            f"Memory 加载: thread={self._thread_id}, {len(messages_data)} 条消息"
        )

    async def save(self) -> None:
        """
        将当前 memory 回写到 DB（Agent 请求结束后调用）。

        流程：加载 DB 历史 → 合并当前内存消息 → Token 截断 → 保存回 DB。
        """
        from app.persistence.turn_repository import TurnRepository

        # 确保已从 DB 加载历史（每个请求周期首次 save 时执行）
        if not self._loaded:
            await self._load_from_db_async()
            self._loaded = True

        repo = TurnRepository(self._db)
        latest_turn = await repo.get_latest_turn(self._thread_id)
        if not latest_turn:
            logger.warning(f"save: thread {self._thread_id} 无 turn，跳过")
            return

        # Token 截断
        truncated = self._token_manager.truncate_messages(self._memory.messages)

        messages = []
        for msg in truncated:
            # 处理 dict (从 DB 加载后是 dict) 和 LangChain Message 对象两种情况
            if isinstance(msg, dict):
                role = msg.get("type") or msg.get("role", "")
                if role == "tool" or msg.get("name"):
                    messages.append({
                        "role": "tool",
                        "name": msg.get("name", ""),
                        "content": msg.get("content", ""),
                    })
                elif role in ("user", "human"):
                    messages.append({"role": "user", "content": msg.get("content", "")})
                elif role in ("assistant", "ai"):
                    messages.append({"role": "assistant", "content": msg.get("content", "")})
                else:
                    # 未知类型，跳过
                    pass
            elif isinstance(msg, HumanMessage):
                messages.append({"role": "user", "content": msg.content})
            elif isinstance(msg, ToolMessage):
                messages.append({
                    "role": "tool",
                    "name": msg.name or "",
                    "content": msg.content,
                })
            elif isinstance(msg, AIMessage):
                messages.append({"role": "assistant", "content": msg.content})

        await repo.save_messages_history(latest_turn.id, messages)
        logger.info(
            f"Memory 已保存: thread={self._thread_id}, "
            f"{len(messages)} 条（截断后，共 {self._token_manager.count_tokens(truncated)} tokens）"
        )


class DBConversationBufferMemory(LazyConversationBufferMemory):
    """DB 持久化版 ConversationBufferMemory"""
    pass
