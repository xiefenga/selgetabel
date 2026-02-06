"""Excel 处理流式执行封装

提供统一的 Excel 处理流程，生成标准化的 SSE 事件流。
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, AsyncGenerator, Awaitable, Callable, Dict, List, Optional

from sse_starlette.sse import ServerSentEvent

from app.api.deps import get_llm_client
from app.core.sse import (
    sse_step_running,
    sse_step_streaming,
    sse_step_done,
    sse_step_error,
)
from app.engine.models import FileCollection, column_index_to_letter
from app.processor import ExcelProcessor, ProcessConfig, EventType
from app.services.oss import upload_file

logger = logging.getLogger(__name__)


# ============ 数据类型定义 ============


@dataclass
class StageContext:
    """阶段上下文，包含事件的所有信息"""

    step: str
    stage_id: str
    event_type: EventType
    output: Optional[Any] = None
    error: Optional[str] = None
    delta: Optional[str] = None


# 回调类型：接收 context，无返回值
StageCallback = Callable[[StageContext], Awaitable[None]]
# 埋点回调：整体流程失败时调用
FailureCallback = Callable[[List], Awaitable[None]]


# ============ 辅助函数 ============


def _dtype_to_friendly(dtype: str) -> str:
    """
    将 pandas dtype 转换为友好的类型名称

    Returns:
        友好的类型名称：number, text, date, boolean
    """
    dtype_lower = dtype.lower()

    if any(t in dtype_lower for t in ["int", "float", "decimal"]):
        return "number"
    if any(t in dtype_lower for t in ["datetime", "date", "time", "timedelta"]):
        return "date"
    if "bool" in dtype_lower:
        return "boolean"
    return "text"


def build_file_collection_info(tables: FileCollection) -> List[Dict[str, Any]]:
    """
    构建 FileCollection 的详细信息

    Returns:
        文件信息数组：
        [
            {
                "file_id": "xxx",
                "filename": "orders.xlsx",
                "sheets": [
                    {
                        "name": "Sheet1",
                        "row_count": 100,
                        "columns": [
                            {"name": "订单号", "letter": "A", "type": "text"},
                            {"name": "金额", "letter": "B", "type": "number"},
                        ]
                    }
                ]
            }
        ]
    """
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

                columns_info.append(
                    {"name": col_name, "letter": col_letter, "type": friendly_type}
                )

            sheet_info = {
                "name": sheet_name,
                "row_count": table.row_count(),
                "columns": columns_info,
            }
            file_info["sheets"].append(sheet_info)

        files_info.append(file_info)

    return files_info


async def _export_modified_files(
    tables: FileCollection,
    modified_file_ids: List[str],
    path_prefix: str,
) -> List[Dict[str, str]]:
    """
    导出被修改的文件到 OSS

    Args:
        tables: 文件集合
        modified_file_ids: 被修改的文件 ID 列表
        path_prefix: OSS 路径前缀

    Returns:
        导出文件列表：[{file_id, filename, url}, ...]
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_files = []

    for file_id in modified_file_ids:
        try:
            file_info = tables.get_file_info(file_id)
            filename = file_info["filename"]

            # 导出单个文件到字节流
            excel_bytes = await asyncio.to_thread(tables.export_file_to_bytes, file_id)

            # 生成对象名称
            object_name = f"{path_prefix}/{timestamp}/{filename}"

            # 上传到 OSS
            public_url = upload_file(
                data=excel_bytes,
                object_name=object_name,
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

            output_files.append(
                {"file_id": file_id, "filename": filename, "url": public_url}
            )

        except Exception as e:
            logger.warning(f"Export file {file_id} failed: {e}")
            # 继续处理其他文件，不中断

    return output_files


# ============ 核心处理流程 ============


async def stream_excel_processing(
    load_tables_fn: Callable[[], Awaitable[FileCollection]],
    query: str,
    stream_llm: bool = True,
    export_path_prefix: Optional[str] = None,
    on_event: Optional[StageCallback] = None,
    on_failure: Optional[FailureCallback] = None,
    on_load_tables: Optional[Callable[[FileCollection], Awaitable[None]]] = None,
) -> AsyncGenerator[ServerSentEvent, None]:
    """
    完整的 Excel 处理流式输出

    统一处理流程：load → generate → validate → execute → export → complete

    Args:
        load_tables_fn: 加载数据的函数（由调用方实现）
        query: 用户查询
        stream_llm: 是否使用流式 LLM
        export_path_prefix: OSS 导出路径前缀，不传则跳过导出
        on_event: 事件回调（用于持久化等副作用）
        on_failure: 整体流程失败回调（用于埋点等副作用）
        on_load_tables: 加载表格后回调（可用于缓存等副作用）

    Yields:
        ServerSentEvent 事件

    Example:
        # chat.py
        async for sse in stream_excel_processing(
            load_tables_fn=lambda: load_from_db(db, file_ids, user_id),
            query=params.query,
            export_path_prefix=f"users/{user_id}/outputs",
            on_event=on_event,
        ):
            yield sse

        # fixture.py
        async for sse in stream_excel_processing(
            load_tables_fn=lambda: ExcelParser.parse_multiple_files(file_paths),
            query=case.prompt,
            export_path_prefix=f"fixture_outputs/{scenario_id}/{case_id}",
        ):
            yield sse
    """

    # === 1. load:file ===
    load_stage_id = str(uuid.uuid4())

    if on_event:
        await on_event(
            StageContext("load", load_stage_id, EventType.STAGE_START)
        )
    yield sse_step_running("load", load_stage_id)

    try:
        tables = await load_tables_fn()
        files_info = build_file_collection_info(tables)
        load_output = {"files": files_info}
        if on_load_tables:
            await on_load_tables(tables)

        if on_event:
            await on_event(
                StageContext(
                    "load", load_stage_id, EventType.STAGE_DONE, output=load_output
                )
            )
        yield sse_step_done("load", load_output, load_stage_id)

    except Exception as e:
        logger.exception(f"Load files error: {e}")
        if on_event:
            await on_event(
                StageContext(
                    "load", load_stage_id, EventType.STAGE_ERROR, error=str(e)
                )
            )
        yield sse_step_error("load", str(e), load_stage_id)
        return

    # === 2. generate/validate/execute ===
    llm_client = get_llm_client()
    processor = ExcelProcessor(llm_client)
    config = ProcessConfig(stream_llm=stream_llm)

    gen = processor.process(tables, query, config)
    _GENERATOR_DONE = object()

    def get_next_event():
        try:
            return next(gen)
        except StopIteration as e:
            return _GENERATOR_DONE, e.value

    result = None
    has_error = False

    while True:
        event_or_done = await asyncio.to_thread(get_next_event)

        if isinstance(event_or_done, tuple) and event_or_done[0] is _GENERATOR_DONE:
            result = event_or_done[1]
            break

        event = event_or_done
        step_name = event.stage.value
        stage_id = event.stage_id

        # execute 阶段：如果 output 中有 errors，转换为 error 事件
        event_type = event.event_type
        error_msg = getattr(event, "error", None)

        if (
            step_name == "execute"
            and event_type == EventType.STAGE_DONE
        ):
            output = event.output or {}
            errors = output.get("errors", [])
            if errors:
                event_type = EventType.STAGE_ERROR
                error_msg = "; ".join(errors) if isinstance(errors, list) else str(errors)

        # 构建上下文并调用回调
        ctx = StageContext(
            step=step_name,
            stage_id=stage_id,
            event_type=event_type,
            output=getattr(event, "output", None),
            error=error_msg,
            delta=getattr(event, "delta", None),
        )

        if on_event:
            await on_event(ctx)

        # 生成 SSE 事件
        if event_type == EventType.STAGE_START:
            yield sse_step_running(step_name, stage_id)

        elif event_type == EventType.STAGE_STREAM:
            yield sse_step_streaming(step_name, event.delta, stage_id)

        elif event_type == EventType.STAGE_DONE:
            yield sse_step_done(step_name, event.output, stage_id)

        elif event_type == EventType.STAGE_ERROR:
            yield sse_step_error(step_name, error_msg, stage_id)
            has_error = True
            # 错误后发送 complete 并终止
            yield sse_step_done(
                "complete", {"success": False, "errors": [error_msg]}
            )
            if on_failure:
                await on_failure([error_msg])
            return

    # === 3. export:result ===
    output_files = None
    modified_file_ids = result.get_modified_file_ids() if result else []

    if (
        export_path_prefix
        and result
        and result.modified_tables
        and modified_file_ids
        and not result.has_errors()
    ):
        export_stage_id = str(uuid.uuid4())

        if on_event:
            await on_event(
                StageContext("export", export_stage_id, EventType.STAGE_START)
            )
        yield sse_step_running("export", export_stage_id)

        try:
            output_files = await _export_modified_files(
                result.modified_tables, modified_file_ids, export_path_prefix
            )
            export_output = {"output_files": output_files}

            if on_event:
                await on_event(
                    StageContext(
                        "export",
                        export_stage_id,
                        EventType.STAGE_DONE,
                        output=export_output,
                    )
                )
            yield sse_step_done("export", export_output, export_stage_id)

        except Exception as e:
            logger.warning(f"Export to OSS failed: {e}")
            if on_event:
                await on_event(
                    StageContext(
                        "export",
                        export_stage_id,
                        EventType.STAGE_ERROR,
                        error=str(e),
                    )
                )
            yield sse_step_error("export", str(e), export_stage_id)

    # === 4. complete ===
    success = result is not None and not result.has_errors()
    errors = result.errors if result and result.errors else None

    if not success and on_failure:
        await on_failure(errors)

    yield sse_step_done("complete", {"success": success, "errors": errors})
