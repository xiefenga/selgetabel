"""ExcelAgent — LangChain Agent 主类"""

import logging
from typing import AsyncGenerator, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.agent_executor import AgentExecutor
from app.agent.langchain_llm import get_langchain_chat_model
from app.agent.memory.db_buffer import DBConversationBufferMemory
from app.agent.streaming import StreamEvent
from app.agent.tools.registry import ExcelToolRegistry

logger = logging.getLogger(__name__)


class ExcelAgent:
    """
    Excel 智能助手 Agent。

    Phase 1/2: use_full_agent=False，走简化工具调度
    Phase 4+: use_full_agent=True，走 langchain.agents.create_agent 完整流程
    """

    def __init__(
        self,
        user_id: UUID,
        thread_id: UUID,
        db_session: AsyncSession,
        stage: str = "chat",
    ):
        self.user_id = user_id
        self.thread_id = thread_id
        self.db = db_session
        self.repo = None  # 延迟初始化
        self.tool_registry = ExcelToolRegistry()
        # 注入请求级上下文到工具（ReadExcelTool 等需要 user_id + db）
        self.tool_registry.set_context(str(user_id), db_session)

        # Memory（Phase 3 实现从 DB 加载/保存）
        self.memory = DBConversationBufferMemory(
            thread_id=thread_id,
            user_id=user_id,
            db_session=db_session,
        )

        self._llm = None
        self._stage = stage

    async def _ensure_llm(self):
        if self._llm is None:
            self._llm = await get_langchain_chat_model(self._stage, self.db)

    def _get_system_prompt(self) -> str:
        """获取系统提示词"""
        from app.agent.prompts.excel_assistant import get_excel_assistant_prompt
        return get_excel_assistant_prompt()

    async def run(
        self,
        query: str,
        file_ids: list[str],
        use_full_agent: bool = False,
    ) -> AsyncGenerator[StreamEvent, None]:
        """
        运行 Agent。

        use_full_agent=False（默认 Phase 1/2）：直接工具调度
        use_full_agent=True（Phase 4+）：ConversableAgent 完整流程
        """
        from app.persistence.turn_repository import TurnRepository

        if self.repo is None:
            self.repo = TurnRepository(self.db)

        executor = AgentExecutor(
            agent=None,
            memory=self.memory,
            tool_registry=self.tool_registry,
        )

        if use_full_agent:
            # Phase 4+: ConversableAgent 完整流程
            await self._ensure_llm()
            system_prompt = self._get_system_prompt()

            async for event in executor.run(
                query=query,
                file_ids=file_ids,
                model=self._llm,
                system_prompt=system_prompt,
            ):
                yield event
        else:
            # Phase 1/2: 简化工具调度
            async for event in executor.run_simple(query=query, file_ids=file_ids):
                yield event

        # 保存 memory（每个请求周期结束时执行）
        try:
            await self.memory.save()
        except Exception as e:
            logger.error(f"保存 memory 失败: {e}")
