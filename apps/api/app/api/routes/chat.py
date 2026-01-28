import json
import asyncio
from typing import List, AsyncGenerator, Optional, Any
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, File, HTTPException, Depends
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse, ServerSentEvent
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm.attributes import flag_modified

from app.api.deps import get_llm_client, get_current_user
from app.core.database import AsyncSessionLocal
from app.models.user import User
from app.models.file import File
from app.models.thread import Thread, ThreadTurn, TurnFile
from app.services.excel import (
    load_tables_from_files,
    get_files_by_ids_from_db,
)
from app.services.thread import generate_thread_title
from app.core.parser import parse_and_validate
from app.core.executor import execute_operations
from app.core.excel_generator import generate_formulas, format_formula_output
from app.core.config import OUTPUT_DIR
from app.core.step_tracker import StepTracker
from app.core.models import ExcelError

router = APIRouter()


# ========== JSON 序列化辅助函数 ==========
def make_json_serializable(obj: Any) -> Any:
    """
    将对象转换为可 JSON 序列化的格式

    主要处理 ExcelError 等自定义类型
    """
    if isinstance(obj, ExcelError):
        return str(obj)  # 转换为字符串，如 "#N/A"
    elif isinstance(obj, dict):
        return {k: make_json_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [make_json_serializable(item) for item in obj]
    elif isinstance(obj, tuple):
        return tuple(make_json_serializable(item) for item in obj)
    else:
        return obj


# ========== SSE 事件类型 ==========
class SSEEvent:
    """SSE 事件类型常量"""
    SESSION = "session"  # 会话元数据事件
    ERROR = "error"      # 会话级/系统级错误事件
    # 业务流程事件使用默认 message，不指定 event


class Step:
    """业务流程步骤常量"""
    LOAD = "load"
    ANALYZE = "analyze"
    GENERATE = "generate"
    EXECUTE = "execute"
    COMPLETE = "complete"


class StepStatus:
    """步骤状态常量"""
    RUNNING = "running"
    STREAMING = "streaming"
    DONE = "done"
    ERROR = "error"


class ErrorCode:
    """错误码常量"""
    # 会话级错误
    THREAD_NOT_FOUND = "THREAD_NOT_FOUND"
    FILE_NOT_FOUND = "FILE_NOT_FOUND"
    INVALID_PARAMS = "INVALID_PARAMS"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    # 步骤级错误
    LOAD_FAILED = "LOAD_FAILED"
    LLM_TIMEOUT = "LLM_TIMEOUT"
    LLM_ERROR = "LLM_ERROR"
    PARSE_FAILED = "PARSE_FAILED"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    EXECUTE_FAILED = "EXECUTE_FAILED"


def sse(data: Any, event: Optional[str] = None) -> ServerSentEvent:
    """创建 SSE 事件"""
    return ServerSentEvent(data=json.dumps(data, ensure_ascii=False), event=event)


def sse_session(thread_id: str, turn_id: str, title: str, is_new_thread: bool) -> ServerSentEvent:
    """创建 session 事件"""
    return sse({
        "thread_id": thread_id,
        "turn_id": turn_id,
        "title": title,
        "is_new_thread": is_new_thread,
    }, event=SSEEvent.SESSION)


def sse_error(code: str, message: str) -> ServerSentEvent:
    """创建 error 事件（会话级/系统级错误）"""
    return sse({"code": code, "message": message}, event=SSEEvent.ERROR)


def sse_step_running(step: str) -> ServerSentEvent:
    """创建步骤开始事件"""
    return sse({"step": step, "status": StepStatus.RUNNING})


def sse_step_streaming(step: str, delta: str) -> ServerSentEvent:
    """创建步骤流式输出事件"""
    return sse({"step": step, "status": StepStatus.STREAMING, "delta": delta})


def sse_step_done(step: str, output: Any) -> ServerSentEvent:
    """创建步骤完成事件"""
    return sse({"step": step, "status": StepStatus.DONE, "output": output})


def sse_step_error(step: str, code: str, message: str) -> ServerSentEvent:
    """创建步骤错误事件"""
    return sse({
        "step": step,
        "status": StepStatus.ERROR,
        "error": {"code": code, "message": message}
    })


async def process_excel_stream(query: str, file_ids: List[UUID], thread_id: Optional[UUID], user_id: UUID, db: AsyncSession) -> AsyncGenerator[ServerSentEvent, None]:
    """
    流式处理 Excel 数据，生成 SSE 事件，并保存到数据库

    SSE 事件协议:
    - event: session  - 会话元数据（thread/turn 创建完成）
    - event: error    - 会话级/系统级错误
    - (default)       - 业务流程步骤 { step, status, delta/output/error }

    步骤数据存储在 ThreadTurn.steps 字段中（JSONB 数组）
    详见 SSE_SPEC.md 和 STEPS_STORAGE_SPEC.md
    """
    turn: Optional[ThreadTurn] = None
    tracker: Optional[StepTracker] = None
    is_new_thread = False

    async def save_steps():
        """保存当前步骤状态到数据库"""
        if turn and tracker:
            # 确保 steps 数据可以 JSON 序列化
            turn.steps = make_json_serializable(tracker.to_list())
            flag_modified(turn, "steps")  # 强制标记 JSONB 字段为脏
            await db.flush()

    try:
        # ========== 创建或获取线程 ==========
        if thread_id:
            # 获取现有线程
            stmt = select(Thread).where(Thread.id == thread_id).where(Thread.user_id == user_id)
            result = await db.execute(stmt)
            thread = result.scalar_one_or_none()
            if not thread:
                yield sse_error(ErrorCode.THREAD_NOT_FOUND, "线程不存在或无权访问")
                return
            title = thread.title
        else:
            # 创建新线程
            is_new_thread = True
            llm_client = get_llm_client()
            title = await asyncio.to_thread(generate_thread_title, query, llm_client)
            thread = Thread(
                id=uuid4(),
                user_id=user_id,
                title=title,
                status="active",
            )
            db.add(thread)
            await db.commit()
            thread_id = thread.id

        # ========== 创建消息记录 ==========
        # 获取下一个 turn_number
        stmt = select(func.max(ThreadTurn.turn_number)).where(ThreadTurn.thread_id == thread_id)
        result = await db.execute(stmt)
        max_turn_number = result.scalar_one_or_none() or 0
        next_turn_number = max_turn_number + 1

        turn = ThreadTurn(
            thread_id=thread_id,
            turn_number=next_turn_number,
            user_query=query,
            status="pending",
            steps=[],
        )
        db.add(turn)
        await db.commit()
        turn_id = turn.id

        # 初始化步骤追踪器
        tracker = StepTracker()

        # ========== 关联文件到消息 ==========
        for file_id in file_ids:
            # 验证文件权限
            stmt = select(File).where(File.id == file_id).where(File.user_id == user_id)
            result = await db.execute(stmt)
            file_record = result.scalar_one_or_none()
            if not file_record:
                yield sse_error(ErrorCode.FILE_NOT_FOUND, f"文件不存在或无权访问: {file_id}")
                return

            # 创建关联
            turn_file = TurnFile(
                id=uuid4(),
                turn_id=turn_id,
                file_id=file_id,
            )
            db.add(turn_file)

        await db.flush()

        # ========== 发送 session 事件 ==========
        yield sse_session(
            thread_id=str(thread_id),
            turn_id=str(turn_id),
            title=title,
            is_new_thread=is_new_thread,
        )

        # ========== 加载文件 ==========
        tracker.start(Step.LOAD)
        yield sse_step_running(Step.LOAD)

        turn.status = "processing"
        turn.started_at = datetime.now(timezone.utc)
        await save_steps()

        try:
            files = await get_files_by_ids_from_db(db, file_ids, user_id)
        except HTTPException as e:
            tracker.error(Step.LOAD, ErrorCode.LOAD_FAILED, e.detail)
            turn.status = "failed"
            await save_steps()
            await db.commit()
            yield sse_step_error(Step.LOAD, ErrorCode.LOAD_FAILED, e.detail)
            return

        if not files:
            tracker.error(Step.LOAD, ErrorCode.LOAD_FAILED, "没有有效的 Excel 文件")
            turn.status = "failed"
            await save_steps()
            await db.commit()
            yield sse_step_error(Step.LOAD, ErrorCode.LOAD_FAILED, "没有有效的 Excel 文件")
            return

        try:
            tables = await asyncio.to_thread(load_tables_from_files, files)
            schemas = tables.get_schemas()
            tracker.done(Step.LOAD, {"schemas": schemas})
            await save_steps()
            yield sse_step_done(Step.LOAD, {"schemas": schemas})
        except HTTPException as e:
            tracker.error(Step.LOAD, ErrorCode.LOAD_FAILED, e.detail)
            turn.status = "failed"
            await save_steps()
            await db.commit()
            yield sse_step_error(Step.LOAD, ErrorCode.LOAD_FAILED, e.detail)
            return

        llm_client = get_llm_client()

        # ========== 需求分析 ==========
        tracker.start(Step.ANALYZE)
        yield sse_step_running(Step.ANALYZE)
        await save_steps()

        try:
            analysis = await asyncio.to_thread(
                llm_client.analyze_requirement, query, schemas
            )
            tracker.done(Step.ANALYZE, {"content": analysis})
            await save_steps()
            yield sse_step_done(Step.ANALYZE, {"content": analysis})
        except Exception as e:
            error_msg = f"需求分析失败: {e}"
            tracker.error(Step.ANALYZE, ErrorCode.LLM_ERROR, error_msg)
            turn.status = "failed"
            await save_steps()
            await db.commit()
            yield sse_step_error(Step.ANALYZE, ErrorCode.LLM_ERROR, error_msg)
            return

        # ========== 生成操作 ==========
        tracker.start(Step.GENERATE)
        yield sse_step_running(Step.GENERATE)
        await save_steps()

        try:
            operations_json = await asyncio.to_thread(
                llm_client.generate_operations, query, analysis, schemas
            )
            operations_dict = json.loads(operations_json)
            tracker.done(Step.GENERATE, {"operations": operations_dict})
            await save_steps()
            yield sse_step_done(Step.GENERATE, {"operations": operations_dict})
        except json.JSONDecodeError:
            error_msg = "LLM 生成的 JSON 格式错误"
            tracker.error(Step.GENERATE, ErrorCode.PARSE_FAILED, error_msg)
            turn.status = "failed"
            await save_steps()
            await db.commit()
            yield sse_step_error(Step.GENERATE, ErrorCode.PARSE_FAILED, error_msg)
            return
        except Exception as e:
            error_msg = f"生成操作失败: {e}"
            tracker.error(Step.GENERATE, ErrorCode.LLM_ERROR, error_msg)
            turn.status = "failed"
            await save_steps()
            await db.commit()
            yield sse_step_error(Step.GENERATE, ErrorCode.LLM_ERROR, error_msg)
            return

        # 解析验证
        operations, parse_errors = parse_and_validate(
            operations_json, tables.get_table_names()
        )

        # ========== 执行操作 ==========
        tracker.start(Step.EXECUTE)
        yield sse_step_running(Step.EXECUTE)
        await save_steps()

        errors = list(parse_errors) if parse_errors else []
        new_columns = {}
        output_file = None
        output_file_path = None
        execution_result = None
        variables = {}
        formulas = None

        if operations and not parse_errors:
            try:
                execution_result = await asyncio.to_thread(execute_operations, operations, tables)

                # 提取变量（转换为可序列化格式）
                variables = make_json_serializable(execution_result.variables)

                # 新列只返回前 10 行预览（转换为可序列化格式）
                for table_name, cols in execution_result.new_columns.items():
                    new_columns[table_name] = {
                        col: make_json_serializable(values[:10]) for col, values in cols.items()
                    }
                errors.extend(execution_result.errors)

                # 导出文件
                if execution_result.new_columns and not execution_result.has_errors():
                    tables.apply_new_columns(execution_result.new_columns)
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    output_filename = f"result_{timestamp}.xlsx"
                    output_path = OUTPUT_DIR / output_filename
                    await asyncio.to_thread(tables.export_to_excel, str(output_path))
                    output_file = output_filename
                    output_file_path = str(output_path)

            except Exception as e:
                errors.append(f"执行失败: {e}")

        # 生成公式
        if operations:
            try:
                excel_formulas = await asyncio.to_thread(generate_formulas, operations, tables)
                formulas = format_formula_output(excel_formulas)
            except Exception:
                pass

        # ========== 保存执行结果 ==========
        execute_output = {
            "formulas": formulas,
            "output_file": output_file_path or output_file,
            "variables": variables if variables else None,
            "new_columns": new_columns if new_columns else None,
            "errors": errors if errors else None,
        }

        if errors:
            error_msg = "; ".join(errors[:3])
            tracker.error(Step.EXECUTE, ErrorCode.EXECUTE_FAILED, error_msg)
            # 即使失败也保存部分结果
            tracker._steps[-1]["output"] = execute_output
            turn.status = "failed"
            await save_steps()
            await db.commit()
            yield sse_step_error(Step.EXECUTE, ErrorCode.EXECUTE_FAILED, error_msg)
        else:
            tracker.done(Step.EXECUTE, execute_output)
            turn.status = "completed"
            turn.completed_at = datetime.now(timezone.utc)

            # 更新线程更新时间
            thread.updated_at = datetime.now(timezone.utc)

            await save_steps()
            await db.commit()

            yield sse_step_done(Step.EXECUTE, {
                "formulas": formulas,
                "output_file": output_file_path or output_file,
            })

            # 发送流程完成事件
            yield sse_step_done(Step.COMPLETE, {
                "thread_id": str(thread_id),
                "turn_id": str(turn_id),
            })

    except Exception as e:
        await db.rollback()
        # 使用新的数据库会话来保存失败状态，避免事务回滚后的状态问题
        if turn and turn.id:
            try:
                async with AsyncSessionLocal() as new_db:
                    # 重新查询 turn 对象
                    stmt = select(ThreadTurn).where(ThreadTurn.id == turn.id)
                    result = await new_db.execute(stmt)
                    turn_to_update = result.scalar_one_or_none()
                    if turn_to_update:
                        turn_to_update.status = "failed"
                        if tracker:
                            # 确保 steps 数据可以 JSON 序列化
                            turn_to_update.steps = make_json_serializable(tracker.to_list())
                        flag_modified(turn_to_update, "steps")
                        await new_db.commit()
            except Exception as save_error:
                # 记录保存失败的错误，但不影响主错误的返回
                import logging
                logging.error(f"Failed to save turn failure state: {save_error}")
        yield sse_error(ErrorCode.INTERNAL_ERROR, f"处理失败: {e}")


class ChatRequest(BaseModel):
    """Excel 处理请求"""
    query: str = Field(..., description="数据处理需求的自然语言描述")
    file_ids: List[str] = Field(..., description="上传文件返回的 file_id 列表（UUID 字符串），支持多个文件")
    thread_id: Optional[str] = Field(None, description="线程 ID（可选，用于继续会话）")


@router.post("/chat", description="使用自然语言描述数据处理需求，LLM 会自动理解并执行相应操作。")
async def process_excel_chat(params: ChatRequest, current_user: User = Depends(get_current_user)):
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
    # 转换 file_ids 为 UUID
    try:
        file_ids_uuid = [UUID(fid) for fid in params.file_ids]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"无效的 file_id 格式: {e}")

    # 转换 thread_id 为 UUID（如果提供）
    thread_id_uuid = None
    if params.thread_id:
        try:
            thread_id_uuid = UUID(params.thread_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="无效的 thread_id 格式")

    # 手动创建数据库会话，以便在整个流式响应期间保持打开
    async def stream_with_db():
        async with AsyncSessionLocal() as db:
            try:
                async for event in process_excel_stream(
                    query=params.query,
                    file_ids=file_ids_uuid,
                    thread_id=thread_id_uuid,
                    user_id=current_user.id,
                    db=db,
                ):
                    yield event
                await db.commit()
            except Exception as error:
                await db.rollback()
                yield sse_error(ErrorCode.INTERNAL_ERROR, f"处理失败: {error}")
            finally:
                await db.close()

    return EventSourceResponse(stream_with_db())


