"""Excel 智能处理接口"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse, ServerSentEvent

from app.api.deps import get_llm_client, get_current_user
from app.core.database import AsyncSessionLocal
from app.engine.step_tracker import StepTracker
from app.models.user import User
from app.persistence import TurnRepository
from app.processor import ExcelProcessor, ProcessConfig, EventType
from app.services.excel import get_files_by_ids_from_db, load_tables_from_files
from app.services.oss import upload_user_file, OSSError
from app.services.thread import generate_thread_title

logger = logging.getLogger(__name__)

router = APIRouter()


# ============ SSE 事件辅助函数 ============


class SSEEventName:
    """SSE 事件名称常量"""

    SESSION = "session"
    ERROR = "error"


class StepStatus:
    """步骤状态常量"""

    RUNNING = "running"
    STREAMING = "streaming"
    DONE = "done"
    ERROR = "error"


class ErrorCode:
    """错误码常量"""

    THREAD_NOT_FOUND = "THREAD_NOT_FOUND"
    FILE_NOT_FOUND = "FILE_NOT_FOUND"
    INVALID_PARAMS = "INVALID_PARAMS"
    INTERNAL_ERROR = "INTERNAL_ERROR"


def _sse(data: Any, event: Optional[str] = None) -> ServerSentEvent:
    """创建 SSE 事件"""
    return ServerSentEvent(data=json.dumps(data, ensure_ascii=False), event=event)


def sse_session(
    thread_id: str,
    turn_id: str,
    title: str,
    is_new_thread: bool,
) -> ServerSentEvent:
    """创建 session 事件"""
    return _sse(
        {
            "thread_id": thread_id,
            "turn_id": turn_id,
            "title": title,
            "is_new_thread": is_new_thread,
        },
        event=SSEEventName.SESSION,
    )


def sse_error(code: str, message: str) -> ServerSentEvent:
    """创建 error 事件（会话级/系统级错误）"""
    return _sse({"code": code, "message": message}, event=SSEEventName.ERROR)


def sse_step_running(step: str, stage_id: Optional[str] = None) -> ServerSentEvent:
    """创建步骤开始事件"""
    data = {"step": step, "status": StepStatus.RUNNING}
    if stage_id:
        data["stage_id"] = stage_id
    return _sse(data)


def sse_step_streaming(step: str, delta: str, stage_id: Optional[str] = None) -> ServerSentEvent:
    """创建步骤流式输出事件"""
    data = {"step": step, "status": StepStatus.STREAMING, "delta": delta}
    if stage_id:
        data["stage_id"] = stage_id
    return _sse(data)


def sse_step_done(step: str, output: Any, stage_id: Optional[str] = None) -> ServerSentEvent:
    """创建步骤完成事件"""
    data = {"step": step, "status": StepStatus.DONE, "output": output}
    if stage_id:
        data["stage_id"] = stage_id
    return _sse(data)


def sse_step_error(step: str, code: str, message: str, stage_id: Optional[str] = None) -> ServerSentEvent:
    """创建步骤错误事件"""
    data = {
        "step": step,
        "status": StepStatus.ERROR,
        "error": {"code": code, "message": message},
    }
    if stage_id:
        data["stage_id"] = stage_id
    return _sse(data)


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
    - load: 加载文件 → { schemas }
    - analyze: 需求分析 → { content }
    - generate: 生成操作 → { operations }
    - execute: 执行操作 → { formulas, output_file }
    - complete: 流程结束 → { thread_id, turn_id }

    详见 SSE_SPEC.md
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
                    yield sse_error(
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
                yield sse_error(ErrorCode.INTERNAL_ERROR, f"初始化会话失败: {e}")
                return

            # === 加载文件 ===
            tracker.start("load")
            yield sse_step_running("load")

            try:
                files = await get_files_by_ids_from_db(db, file_ids, current_user.id)
                tables = await asyncio.to_thread(load_tables_from_files, files)
                schemas = tables.get_schemas()

                tracker.done("load", {"schemas": schemas})
                await repo.save_steps(turn_id, tracker)
                yield sse_step_done("load", {"schemas": schemas})

            except Exception as e:
                logger.exception(f"Load files error: {e}")
                tracker.error("load", "LOAD_FAILED", str(e))
                await repo.mark_failed(turn_id, tracker)
                await repo.commit()
                yield sse_step_error("load", "LOAD_FAILED", str(e))
                return

            # === 核心处理（使用 ExcelProcessor）===
            llm_client = get_llm_client()
            processor = ExcelProcessor(llm_client)
            config = ProcessConfig(stream_llm=True)

            # 标记处理中
            await repo.mark_processing(turn_id, tracker)

            # 执行处理并转换事件
            gen = processor.process(tables, params.query, config)
            _GENERATOR_DONE = object()  # 哨兵值，标记生成器结束

            def get_next_event():
                """在线程中获取下一个事件，避免阻塞事件循环"""
                try:
                    return next(gen)
                except StopIteration as e:
                    # StopIteration 不能通过 asyncio.to_thread 正常传播
                    # 返回哨兵值和结果
                    return _GENERATOR_DONE, e.value

            result = None
            while True:
                # 使用 asyncio.to_thread 避免阻塞事件循环
                event_or_done = await asyncio.to_thread(get_next_event)

                # 检查是否结束
                if isinstance(event_or_done, tuple) and event_or_done[0] is _GENERATOR_DONE:
                    result = event_or_done[1]
                    break

                event = event_or_done
                step_name = event.stage.value
                stage_id = event.stage_id

                if event.event_type == EventType.STAGE_START:
                    tracker.start(step_name)
                    yield sse_step_running(step_name, stage_id)

                elif event.event_type == EventType.STAGE_STREAM:
                    yield sse_step_streaming(step_name, event.delta, stage_id)

                elif event.event_type == EventType.STAGE_DONE:
                    tracker.done(step_name, event.output)
                    await repo.save_steps(turn_id, tracker)
                    yield sse_step_done(step_name, event.output, stage_id)

                elif event.event_type == EventType.STAGE_ERROR:
                    tracker.error(step_name, "STEP_ERROR", event.error)
                    await repo.mark_failed(turn_id, tracker)
                    await repo.commit()
                    yield sse_step_error(step_name, "STEP_ERROR", event.error, stage_id)
                    return

            # === 导出结果到 OSS ===
            output_file_url = None
            if result.modified_tables and not result.has_errors():
                try:
                    output_file_url = await _export_to_oss(
                        result.modified_tables, str(current_user.id)
                    )
                except Exception as e:
                    logger.warning(f"Export to OSS failed: {e}")

            # 更新 execute 步骤的输出（添加 output_file）
            if output_file_url:
                execute_record = tracker.get_latest("execute")
                if execute_record and execute_record.get("output"):
                    execute_record["output"]["output_file"] = output_file_url
                    await repo.save_steps(turn_id, tracker)
                    # 重新发送 execute done 事件（带 output_file）
                    yield sse_step_done("execute", execute_record["output"])

            # === 完成 ===
            await repo.mark_completed(turn_id, actual_thread_id, tracker)
            await repo.commit()

            yield sse_step_done(
                "complete",
                {
                    "thread_id": str(actual_thread_id),
                    "turn_id": str(turn_id),
                },
            )

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
            return {"error": {"code": ErrorCode.THREAD_NOT_FOUND, "message": "线程不存在或无权访问"}}
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


async def _export_to_oss(tables, user_id: str) -> str:
    """
    导出结果文件到 OSS

    Args:
        tables: FileCollection
        user_id: 用户 ID

    Returns:
        OSS 公共访问 URL
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"result_{timestamp}.xlsx"

    # 导出到字节流
    excel_bytes = await asyncio.to_thread(tables.export_to_bytes)

    # 上传到 OSS
    file_id, object_name, public_url = upload_user_file(
        data=excel_bytes,
        user_id=user_id,
        filename=output_filename,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        size=len(excel_bytes),
        prefix="outputs",
    )
    return public_url
