"""分析流式响应 - 复用 chat 逻辑，直接流式返回分析结果

绕过 ExcelProcessor 的 step 跟踪机制，避免 JSON 序列化问题。
"""

import asyncio
import json
import logging
from typing import AsyncGenerator, List, Optional
from uuid import UUID

import numpy as np
from sse_starlette.sse import ServerSentEvent

from app.api.deps import get_llm_client
from app.core.sse import sse
from app.engine.step_tracker import StepTracker
from app.models.btrack import BTrack
from app.persistence import TurnRepository
from app.persistence.turn_repository import make_json_serializable
from app.services.excel import get_files_by_ids_from_db, load_tables_from_files
from app.services.thread import generate_thread_title

logger = logging.getLogger(__name__)


def _serialize_steps(tracker: StepTracker) -> list:
    """将 tracker.to_list() 序列化为完全兼容 JSON 的纯 Python 对象"""
    raw = make_json_serializable(tracker.to_list())

    def _convert(obj):
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, np.bool_):
            return bool(obj)
        if isinstance(obj, dict):
            return {k: _convert(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_convert(i) for i in obj]
        if isinstance(obj, tuple):
            return tuple(_convert(i) for i in obj)
        return obj

    cleaned = _convert(raw)
    return json.loads(json.dumps(cleaned))


async def stream_analysis_response(
    *,
    query: str,
    user_id: UUID,
    thread_id: Optional[str],
    db,
    file_ids: List[UUID],
    intent_context: dict,
) -> AsyncGenerator[ServerSentEvent, None]:
    """
    分析意图的流式响应，逻辑与 stream_chat_response 完全一致：

    1. 获取/创建 thread
    2. yield session 事件
    3. 加载数据、提取画像、流式返回分析
    4. yield complete 事件

    不经过 ExcelProcessor，无 step 跟踪，无 JSON 序列化问题。
    """
    # === 1. 会话初始化 ===
    repo = TurnRepository(db)
    actual_thread_id = thread_id
    is_new_thread = False

    if not actual_thread_id:
        llm_client = await get_llm_client(db)
        title = await asyncio.to_thread(generate_thread_title, query, llm_client)
        thread = await repo.create_thread(user_id, title)
        actual_thread_id = str(thread.id)
        is_new_thread = True

    # === 2. session 事件 ===
    yield sse(
        {"thread_id": actual_thread_id, "intent": "analysis"},
        event="session",
    )

    tracker = StepTracker()
    turn_id = None

    try:
        # === 3. 创建 turn ===
        turn_number = await repo.get_next_turn_number(UUID(actual_thread_id))
        turn = await repo.create_turn(
            thread_id=UUID(actual_thread_id),
            turn_number=turn_number,
            user_query=query,
            intent_type="analysis",
        )
        turn_id = turn.id

        # 关联文件
        if file_ids:
            await repo.link_files_to_turn(turn_id, file_ids, user_id)

        await repo.commit()

        # === 4. 标记处理中 ===
        tracker.start("load")
        yield sse({"step": "load", "status": "running"}, event="message")

        # === 5. 加载数据 ===
        try:
            files = await get_files_by_ids_from_db(db, file_ids, user_id)
            tables = await asyncio.to_thread(load_tables_from_files, files)
        except Exception as e:
            logger.error(f"加载文件失败: {e}")
            yield sse({"step": "load", "status": "done", "output": {"files": []}}, event="message")
            raise

        # 构建文件信息
        files_info = _build_file_info(tables)
        tracker.done("load", {"files": files_info})
        yield sse({"step": "load", "status": "done", "output": {"files": files_info}}, event="message")

        # === 6. 分析阶段 ===
        tracker.start("analyze")
        yield sse({"step": "analyze", "status": "running"}, event="message")

        # 提取数据画像和质量报告
        profile_text, quality_text = await asyncio.to_thread(
            _extract_profile_and_quality, tables
        )

        # 检测场景
        scenario = _detect_scenario(query)

        # 构建分析提示词
        analysis_prompt = await asyncio.to_thread(
            _build_analysis_prompt,
            scenario=scenario,
            query=query,
            profile_text=profile_text,
            quality_text=quality_text,
        )

        # 流式调用 LLM（使用后台线程 + 队列，避免阻塞事件循环）
        llm_client = await get_llm_client(db)
        full_reply = ""

        queue: asyncio.Queue[tuple[str, str] | None | Exception] = asyncio.Queue()

        def stream_in_thread():
            """在后台线程中执行流式调用"""
            try:
                for delta, full_content in llm_client.analyze_stream(analysis_prompt):
                    queue.put_nowait((delta, full_content))
                queue.put_nowait(None)  # 结束信号
            except Exception as e:
                logger.error(f"LLM 流式调用异常: {e}")
                queue.put_nowait(e)

        try:
            # 在后台线程中启动流式调用
            loop = asyncio.get_running_loop()
            loop.run_in_executor(None, stream_in_thread)

            # 从队列中读取数据并实时推送
            while True:
                item = await queue.get()
                if item is None:
                    break
                if isinstance(item, Exception):
                    raise item
                delta, _ = item
                if delta:
                    full_reply += delta
                    yield sse(
                        {"step": "analyze", "status": "streaming", "delta": delta},
                        event="message",
                    )
        except Exception as llm_err:
            logger.error(f"流式 LLM 调用失败: {llm_err}")
            # fallback 到非流式
            try:
                full_reply = await asyncio.to_thread(llm_client.analyze, analysis_prompt)
                if full_reply:
                    yield sse(
                        {"step": "analyze", "status": "streaming", "delta": full_reply},
                        event="message",
                    )
                else:
                    full_reply = "抱歉，分析过程中遇到问题，请稍后再试。"
            except Exception as fallback_err:
                logger.error(f"非流式 fallback 也失败: {fallback_err}")
                full_reply = "抱歉，分析过程中遇到问题，请稍后再试。"

        tracker.done("analyze", {"content": full_reply, "analysis_type": scenario})
        yield sse(
            {"step": "analyze", "status": "done", "output": {"content": full_reply, "analysis_type": scenario}},
            event="message",
        )

        # === 7. 保存 turn（不走 ExcelProcessor，直接落库）===
        from datetime import datetime, timezone as tz
        now = datetime.now(tz.utc)

        try:
            turn.response_text = full_reply
            turn.status = "completed"
            turn.completed_at = now
            turn.updated_at = now
            turn.steps = _serialize_steps(tracker)
            await repo.commit()
        except Exception as save_err:
            logger.error(f"保存 analysis turn 失败: {save_err}", exc_info=True)

    except Exception as e:
        logger.error(f"分析流程异常: {e}", exc_info=True)
        error_msg = f"分析失败: {str(e)}"

        # 保存失败 turn
        if turn_id:
            try:
                turn = await repo.get_turn(turn_id)
                if turn:
                    turn.status = "failed"
                    turn.steps = _serialize_steps(tracker)
                    await repo.commit()
            except Exception:
                pass

        yield sse(
            {"step": "analyze", "status": "done", "output": error_msg},
            event="message",
        )

    # === 8. complete ===
    yield sse({"step": "complete", "status": "done"}, event="message")


# ============ 辅助函数 ============


def _build_file_info(tables) -> List[dict]:
    """构建文件信息列表"""
    from app.engine.models import column_index_to_letter

    files_info = []
    for excel_file in tables:
        file_info = {
            "file_id": excel_file.file_id,
            "filename": excel_file.filename,
            "sheets": [],
        }
        for sheet_name in excel_file.get_sheet_names():
            table = excel_file.get_sheet(sheet_name)
            df = table.get_data()
            columns_info = []
            for idx, col_name in enumerate(table.get_columns()):
                col_letter = column_index_to_letter(idx)
                dtype = str(df[col_name].dtype)
                friendly_type = _dtype_to_friendly(dtype)
                columns_info.append({"name": col_name, "letter": col_letter, "type": friendly_type})
            file_info["sheets"].append({
                "name": sheet_name,
                "row_count": table.row_count(),
                "columns": columns_info,
            })
        files_info.append(file_info)
    return files_info


def _dtype_to_friendly(dtype: str) -> str:
    """将 pandas dtype 转换为友好类型名称"""
    dtype_lower = dtype.lower()
    if any(t in dtype_lower for t in ["int", "float", "decimal"]):
        return "number"
    if any(t in dtype_lower for t in ["datetime", "date", "time", "timedelta"]):
        return "date"
    if "bool" in dtype_lower:
        return "boolean"
    return "text"


def _extract_profile_and_quality(tables):
    """
    提取数据画像和质量报告（同步函数，在线程池中运行）
    """
    from app.engine.data_profiler import DataProfiler
    from app.engine.quality_checker import QualityChecker

    profiler = DataProfiler()
    quality_checker = QualityChecker()

    multi_profile = profiler.profile_tables(tables, for_llm=True)
    profile_text = profiler.format_multi_profile_for_llm(multi_profile)

    quality_reports = []
    for table_name in [p.table_name for p in multi_profile.profiles.values()]:
        for excel_file in tables:
            if excel_file.has_sheet(table_name):
                table = excel_file.get_sheet(table_name)
                report = quality_checker.check_quality(table)
                quality_reports.append(report)
                break

    quality_text = "\n\n".join([
        quality_checker.format_report_for_llm(report)
        for report in quality_reports
    ])

    return profile_text, quality_text


def _detect_scenario(query: str) -> str:
    """检测分析场景"""
    from app.engine.prompt import detect_analysis_scenario
    return detect_analysis_scenario(query)


def _build_analysis_prompt(
    scenario: str,
    query: str,
    profile_text: str,
    quality_text: str,
) -> str:
    """构建分析提示词"""
    from app.engine.prompt import get_analysis_prompt
    return get_analysis_prompt(
        scenario=scenario,
        query=query,
        profile_text=profile_text,
        quality_text=quality_text or "未检测到明显质量问题",
    )
