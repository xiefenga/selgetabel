"""聊天路由 - LangChain Agent 统一入口端点"""

import logging
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.agent.excel_agent import ExcelAgent
from app.agent.streaming import StreamEvent
from app.persistence.turn_repository import TurnRepository
from app.core.sse import sse as make_sse_event

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat")


class ChatRequest(BaseModel):
    """聊天请求"""

    query: str = Field(..., description="用户查询的自然语言描述")
    file_ids: List[str] = Field(
        default_factory=list,
        description="上传文件返回的 file_id 列表（UUID 字符串），支持多个文件",
    )
    thread_id: Optional[str] = Field(None, description="线程 ID（可选，用于继续会话）")


@router.post("")
async def chat(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    LangChain Agent 统一入口（SSE 流式）。

    Phase 1：HelloTool + ClarifyTool 验收。
    Phase 2+：完整工具链。
    """
    async def stream():
        try:
            repo = TurnRepository(db)

            # 获取或创建线程
            thread_uuid = UUID(request.thread_id) if request.thread_id else None
            thread, is_new = await repo.get_or_create_thread(
                user_id=current_user.id,
                thread_id=thread_uuid,
                initial_query=request.query,
            )

            # 创建新 Turn（用于保存 memory）
            next_turn_number = await repo.get_next_turn_number(thread.id)
            current_turn = await repo.create_turn(
                thread_id=thread.id,
                turn_number=next_turn_number,
                user_query=request.query,
            )

            # 关联文件
            if request.file_ids:
                file_uuids = [UUID(fid) for fid in request.file_ids]
                try:
                    await repo.link_files_to_turn(current_turn.id, file_uuids, current_user.id)
                except ValueError as e:
                    yield make_sse_event(
                        {"code": "INVALID_FILE_IDS", "message": str(e)},
                        event="error",
                    )
                    return

            await repo.commit()

            # session 事件（告知前端 thread_id）
            yield make_sse_event(
                {"thread_id": str(thread.id), "is_new": is_new},
                event="session"
            )

            # 建立 Agent（Phase 1 stage = "chat"）
            agent = ExcelAgent(
                user_id=current_user.id,
                thread_id=thread.id,
                db_session=db,
                stage="chat",
            )

            # Agent 执行（use_full_agent=True 启用完整 LangChain Agent）
            response_text = ""
            async for event in agent.run(
                query=request.query,
                file_ids=request.file_ids,
                use_full_agent=True,
            ):
                # 收集最终回复（用于持久化到 turn.response_text）
                if event.event == "agent_end":
                    response_text = event.data.get("response", "")
                yield make_sse_event(event.data, event=event.event)

            # SSE 流结束后，更新 turn 的 response_text（刷新页面时前端从这里读取）
            if response_text:
                try:
                    current_turn.response_text = response_text
                    current_turn.status = "completed"
                    await repo.commit()
                except Exception as e:
                    logger.warning(f"更新 turn response_text 失败: {e}")

            yield make_sse_event({"status": "done"}, event="complete")

        except Exception as e:
            logger.error(f"Agent 执行失败: {e}", exc_info=True)
            yield make_sse_event({"message": f"处理失败: {str(e)}"}, event="error")

    return EventSourceResponse(
        stream(),
        media_type="text/event-stream",
    )
