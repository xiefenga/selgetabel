"""Excel 智能处理接口"""

import asyncio
import json
import logging
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse, ServerSentEvent

from app.api.deps import get_llm_client, get_current_user
from app.core.sse import sse
from app.engine import FileCollection
from app.models.btrack import BTrack
from app.processor.prompt import build_initial_user_message
from app.services.processor_stream import (
    stream_excel_processing,
    StageContext,
)
from app.core.database import AsyncSessionLocal
from app.engine.step_tracker import StepTracker
from app.models.user import User
from app.persistence import TurnRepository
from app.processor import EventType
from app.services.excel import get_files_by_ids_from_db, load_tables_from_files
from app.services.thread import generate_thread_title

logger = logging.getLogger(__name__)

router = APIRouter()


# ============ SSE 事件辅助函数（chat.py 特有）============


class ErrorCode:
    """错误码常量"""

    THREAD_NOT_FOUND = "THREAD_NOT_FOUND"
    FILE_NOT_FOUND = "FILE_NOT_FOUND"
    INVALID_PARAMS = "INVALID_PARAMS"
    INTERNAL_ERROR = "INTERNAL_ERROR"


def sse_session(
    thread_id: str,
    turn_id: str,
    title: str,
    is_new_thread: bool,
) -> ServerSentEvent:
    """创建 session 事件"""
    return sse(
        {
            "thread_id": thread_id,
            "turn_id": turn_id,
            "title": title,
            "is_new_thread": is_new_thread,
        },
        event="session",
    )


def sse_session_error(code: str, message: str) -> ServerSentEvent:
    """创建会话级错误事件"""
    return sse({"code": code, "message": message}, event="error")


# ============ Request Model ============


class ChatRequest(BaseModel):
    """Excel 处理请求"""

    query: str = Field(..., description="数据处理需求的自然语言描述")
    file_ids: List[str] = Field(
        ..., description="上传文件返回的 file_id 列表（UUID 字符串），支持多个文件"
    )
    thread_id: Optional[str] = Field(None, description="线程 ID（可选，用于继续会话）")


# ============ API Endpoint ============


@router.post(
    "/chat",
    description="使用自然语言描述数据处理需求，LLM 会自动理解并执行相应操作。",
)
async def process_excel_chat(
    params: ChatRequest,
    current_user: User = Depends(get_current_user),
):
    """
    使用 LLM 智能处理 Excel 数据（SSE 流式响应）

    SSE 事件协议:
    - event: session  - 会话元数据（thread/turn 创建完成）
    - event: error    - 会话级/系统级错误
    - (default)       - 业务流程步骤 { step, status, delta/output/error }

    业务流程步骤:
    - load:file: 加载文件 → { files }
    - analyze: 需求分析 → { content }
    - generate: 生成操作 → { operations }
    - execute: 执行操作 → { formulas, ... }
    - export:result: 导出结果 → { output_files }
    - complete: 流程结束 → { success, errors }
    """
    # 1. 参数验证和转换
    try:
        file_ids = [UUID(fid) for fid in params.file_ids]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"无效的 file_id 格式: {e}")

    thread_id = None
    if params.thread_id:
        try:
            thread_id = UUID(params.thread_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="无效的 thread_id 格式")

    # 2. 创建流式响应
    async def stream():
        async with AsyncSessionLocal() as db:
            repo = TurnRepository(db)
            tracker = StepTracker()

            # === 会话初始化 ===
            try:
                session_result = await _init_session(
                    repo, current_user.id, params.query, file_ids, thread_id
                )
                if session_result.get("error"):
                    yield sse_session_error(
                        session_result["error"]["code"],
                        session_result["error"]["message"],
                    )
                    return

                yield sse_session(
                    session_result["thread_id"],
                    session_result["turn_id"],
                    session_result["title"],
                    session_result["is_new_thread"],
                )

                turn_id = UUID(session_result["turn_id"])
                actual_thread_id = UUID(session_result["thread_id"])

            except Exception as e:
                logger.exception(f"Session init error: {e}")
                yield sse_session_error(ErrorCode.INTERNAL_ERROR, f"初始化会话失败: {e}")
                return

            # === Excel 处理流程（使用公共模块）===
            # 标记处理中
            await repo.mark_processing(turn_id, tracker)

            # 事件回调：处理持久化
            async def on_event(ctx: StageContext):
                if ctx.event_type == EventType.STAGE_START:
                    tracker.start(ctx.step)
                elif ctx.event_type == EventType.STAGE_DONE:
                    tracker.done(ctx.step, ctx.output)
                    await repo.save_steps(turn_id, tracker)
                elif ctx.event_type == EventType.STAGE_ERROR:
                    tracker.error(ctx.step, "STEP_ERROR", ctx.error)
                    await repo.mark_failed(turn_id, tracker)
                    await repo.commit()

            # 加载文件的函数
            async def load_tables():
                files = await get_files_by_ids_from_db(db, file_ids, current_user.id)
                return await asyncio.to_thread(load_tables_from_files, files)

            process_with_errors = False
            process_errors = []

            async def on_failure(errors: List[str]):
                nonlocal process_errors
                process_errors.extend(errors)
                nonlocal process_with_errors
                process_with_errors = True

            file_collection: Optional[FileCollection] = None

            async def on_load_tables(tables: FileCollection):
                nonlocal file_collection
                file_collection = tables

            # 执行处理流程
            async for sse_event in stream_excel_processing(
                load_tables_fn=load_tables,
                query=params.query,
                stream_llm=True,
                export_path_prefix=f"users/{current_user.id}/outputs",
                on_event=on_event,
                on_failure=on_failure,
                on_load_tables=on_load_tables,
            ):
                yield sse_event

            # === 完成 ===
            await repo.mark_completed(turn_id, actual_thread_id, tracker)
            await repo.commit()

            if process_with_errors:
                db.add(
                    BTrack(
                        reporter_id=current_user.id,
                        steps=tracker.to_list(),
                        errors=json.dumps(process_errors, ensure_ascii=False),
                        thread_turn_id=turn_id,
                        generation_prompt=build_initial_user_message(params.query,  file_collection.get_schemas_with_samples(sample_count=3))
                    )
                )
                await db.commit()

    return EventSourceResponse(stream())


# ============ Helper Functions ============


async def _init_session(
    repo: TurnRepository,
    user_id: UUID,
    query: str,
    file_ids: List[UUID],
    thread_id: Optional[UUID],
) -> dict:
    """
    初始化会话

    创建或获取 Thread，创建 Turn，关联文件。

    Returns:
        {
            "thread_id": str,
            "turn_id": str,
            "title": str,
            "is_new_thread": bool,
            "error": Optional[{"code": str, "message": str}]
        }
    """
    is_new_thread = False
    title = ""

    # 获取或创建线程
    if thread_id:
        thread = await repo.get_thread(thread_id, user_id)
        if not thread:
            return {
                "error": {
                    "code": ErrorCode.THREAD_NOT_FOUND,
                    "message": "线程不存在或无权访问",
                }
            }
        title = thread.title or ""
    else:
        # 创建新线程
        llm_client = get_llm_client()
        title = await asyncio.to_thread(generate_thread_title, query, llm_client)
        thread = await repo.create_thread(user_id, title)
        thread_id = thread.id
        is_new_thread = True

    # 创建 turn
    turn_number = await repo.get_next_turn_number(thread_id)
    turn = await repo.create_turn(thread_id, turn_number, query)

    # 关联文件
    try:
        await repo.link_files_to_turn(turn.id, file_ids, user_id)
    except ValueError as e:
        return {"error": {"code": ErrorCode.FILE_NOT_FOUND, "message": str(e)}}

    await repo.commit()

    return {
        "thread_id": str(thread_id),
        "turn_id": str(turn.id),
        "title": title,
        "is_new_thread": is_new_thread,
    }
