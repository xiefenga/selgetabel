"""处理管线"""

import asyncio
import json
import logging
from typing import AsyncGenerator, List, Optional
from uuid import UUID

from sse_starlette.sse import ServerSentEvent

from app.api.deps import get_llm_client
from app.core.sse import sse, sse_session, sse_session_error
from app.engine.step_tracker import StepTracker
from app.models.btrack import BTrack
from app.persistence import TurnRepository
from app.processor import EventType
from app.processor.prompt import build_initial_user_message
from app.services.excel import get_files_by_ids_from_db, load_tables_from_files
from app.services.processor_stream import StageContext, stream_excel_processing
from app.services.thread import generate_thread_title

logger = logging.getLogger(__name__)


# ============ Error Codes ============


class ErrorCode:
    """错误码常量"""

    THREAD_NOT_FOUND = "THREAD_NOT_FOUND"
    FILE_NOT_FOUND = "FILE_NOT_FOUND"
    INVALID_PARAMS = "INVALID_PARAMS"
    INTERNAL_ERROR = "INTERNAL_ERROR"


# ============ Public Functions ============


async def init_session(
    repo: TurnRepository,
    user_id: UUID,
    query: str,
    file_ids: List[UUID],
    thread_id: Optional[UUID],
    parent_turn_id: Optional[UUID] = None,
    context_snapshot: Optional[dict] = None,
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
        llm_client = await get_llm_client(repo.db)
        title = await asyncio.to_thread(generate_thread_title, query, llm_client)
        thread = await repo.create_thread(user_id, title)
        thread_id = thread.id
        is_new_thread = True

    # 创建 turn（支持父轮次ID和上下文快照）
    turn_number = await repo.get_next_turn_number(thread_id)
    turn = await repo.create_turn(
        thread_id=thread_id,
        turn_number=turn_number,
        user_query=query,
        parent_turn_id=parent_turn_id,
        context_snapshot=context_snapshot,
    )

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


async def build_enhanced_query(
    repo: TurnRepository,
    thread_id: UUID,
    original_query: str,
    history_limit: int = 3,
) -> str:
    """
    获取最近历史轮次拼接增强 query。

    如果有历史对话记录，将其作为背景拼接到当前 query 前。
    """
    try:
        recent_turns = await repo.get_thread_turns(thread_id, limit=history_limit)

        # recent_turns 是倒序的（包含刚刚创建的当前轮次）
        # 如果记录大于1条，说明有历史记录可以参考
        if recent_turns and len(recent_turns) > 1:
            history_text = ""
            # 排除刚创建的当前轮次(recent_turns[0])，取之前的轮次并反转回正序
            for t in reversed(recent_turns[1:]):
                if t.user_query:
                    history_text += f"用户: {t.user_query}\n"
                if t.response_text:
                    history_text += f"助手: {t.response_text}\n"

            if history_text:
                enhanced = (
                    f"【历史对话背景】\n{history_text}\n"
                    f"【当前用户最新指令】\n{original_query}\n\n"
                    f"⚠️ 核心处理规则：\n"
                    f"1. 【独立新任务】：如果“当前用户最新指令”是一个完整的、全新的数据处理需求（例如“筛选出xxx”、“计算xxx”、“找出xxx”等），请**完全忽略**历史背景，仅针对最新指令生成操作。\n"
                    f"2. 【上下文补全】：如果“当前用户最新指令”非常简短，且明显是针对上一轮操作的补充或修改（例如“改为降序”、“那某某列呢”、“不对，是按A列”等），请结合“历史对话背景”补全意图后执行。\n\n"
                    f"请务必先判断指令类型，严格遵循上述规则，生成针对“当前用户最新指令”的数据处理操作。"
                )
                logger.info(f"🧩 组装增强版处理需求: \n{enhanced}")
                return enhanced
    except Exception as e:
        logger.warning(f"获取历史对话构建增强查询失败: {e}")

    return original_query


async def stream_processing_pipeline(
    *,
    db,
    user_id: UUID,
    query: str,
    file_ids: List[UUID],
    thread_id: Optional[UUID],
    intent_type: Optional[str] = None,
    intent_context: Optional[dict] = None,
    enhance_query_with_history: bool = False,
    history_limit: int = 3,
) -> AsyncGenerator[ServerSentEvent, None]:
    """
    完整处理管线：init_session → mark_processing → stream_excel_processing → mark_completed → BTrack

    Args:
        db: 数据库 session
        user_id: 用户 ID
        query: 用户查询
        file_ids: 文件 ID 列表（UUID）
        thread_id: 线程 ID（可选）
        intent_type: 意图类型。有值时 session 事件格式为 {"thread_id", "intent"}，
                     为 None 时格式为 {"thread_id", "turn_id", "title", "is_new_thread"}
        intent_context: 上下文快照（可选，来自意图识别结果）
        enhance_query_with_history: 是否用历史对话增强 query
        history_limit: 历史对话轮次数限制
    """
    repo = TurnRepository(db)
    tracker = StepTracker()

    # === 会话初始化 ===
    session_result = await init_session(repo, user_id, query, file_ids, thread_id)

    if session_result.get("error"):
        yield sse_session_error(
            session_result["error"]["code"],
            session_result["error"]["message"],
        )
        return

    turn_id = UUID(session_result["turn_id"])
    actual_thread_id = session_result["thread_id"]

    # === 发送 session 事件 ===
    if intent_type is not None:
        yield sse(
            {"thread_id": actual_thread_id, "intent": intent_type},
            event="session",
        )
    else:
        yield sse_session(
            session_result["thread_id"],
            session_result["turn_id"],
            session_result["title"],
            session_result["is_new_thread"],
        )

    # === 保存上下文快照 ===
    if intent_context and "context_type" in intent_context:
        try:
            from app.services.context_service import get_context_service

            context_service = await get_context_service(db)
            await context_service.save_context_snapshot(turn_id, intent_context)
        except Exception as e:
            logger.warning(f"保存上下文快照失败（不影响主流程）: {e}")

    # === 标记处理中 ===
    await repo.mark_processing(turn_id, tracker)

    # === 增强 query ===
    enhanced_query = query
    if enhance_query_with_history:
        enhanced_query = await build_enhanced_query(
            repo, UUID(actual_thread_id), query, history_limit
        )

    # === 事件回调 ===
    async def on_event(ctx: StageContext):
        if ctx.event_type == EventType.STAGE_START:
            tracker.start(ctx.step)
        elif ctx.event_type == EventType.STAGE_DONE:
            tracker.done(ctx.step, ctx.output)
            await repo.save_steps(turn_id, tracker)
        elif ctx.event_type == EventType.STAGE_ERROR:
            error_keywords = ["请检查", "请指定", "不完整", "LLM 无法处理"]
            if ctx.error and any(kw in ctx.error for kw in error_keywords):
                 try:
                     tracker.error(ctx.step, "INTERRUPTED", "需要用户补充信息")
                 except Exception:
                     pass

                 tracker.start("clarify")
                 tracker.done("clarify", {"message": ctx.error})

                 await repo.save_steps(turn_id, tracker)
                 await repo.commit()
            else:
                 tracker.error(ctx.step, "STEP_ERROR", ctx.error)
                 await repo.mark_failed(turn_id, actual_thread_id, tracker)
                 await repo.commit()

    async def load_tables():
        files = await get_files_by_ids_from_db(db, file_ids, user_id)
        return await asyncio.to_thread(load_tables_from_files, files)

    process_with_errors = False
    process_errors: List[str] = []

    async def on_failure(errors: List[str]):
        nonlocal process_errors, process_with_errors
        process_errors.extend(errors)
        process_with_errors = True

    file_collection = None

    async def on_load_tables(tables):
        nonlocal file_collection
        file_collection = tables

    # === 执行处理流程 ===
    async for sse_event in stream_excel_processing(
        load_tables_fn=load_tables,
        query=enhanced_query,
        stream_llm=True,
        export_path_prefix=f"users/{user_id}/outputs",
        on_event=on_event,
        on_failure=on_failure,
        on_load_tables=on_load_tables,
        intent_type=intent_type,
    ):
        yield sse_event

    # === 完成 ===
    await repo.mark_completed(turn_id, UUID(actual_thread_id), tracker)
    await repo.commit()

    # === BTrack ===
    if process_with_errors and file_collection:
        db.add(
            BTrack(
                reporter_id=user_id,
                steps=tracker.to_list(),
                errors=json.dumps(process_errors, ensure_ascii=False),
                thread_turn_id=turn_id,
                generation_prompt=build_initial_user_message(
                    query,
                    file_collection.get_schemas_with_samples(sample_count=3),
                ),
            )
        )
        await db.commit()
