import json
import asyncio
from typing import List, AsyncGenerator, Optional
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse, ServerSentEvent
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.schemas.response import UploadItem, ApiResponse
from app.api.deps import get_llm_client, get_current_user
from app.core.database import get_db, AsyncSessionLocal
from app.models.user import User
from app.models.file import File
from app.models.thread import Thread, ThreadTurn, TurnResult, TurnFile
from app.services.excel import (
    load_tables_from_files,
    save_upload_file,
    save_file_to_database,
    get_files_by_ids_from_db,
)
from app.services.thread import generate_thread_title
from app.core.parser import parse_and_validate
from app.core.executor import execute_operations
from app.core.excel_generator import generate_formulas, format_formula_output
from app.core.config import OUTPUT_DIR

router = APIRouter()

def sse(action: str, status: str, data: dict = None) -> ServerSentEvent:
    """生成统一格式的 SSE 事件"""
    payload = {"action": action, "status": status}
    if data is not None:
        payload["data"] = data
    return ServerSentEvent(data=json.dumps(payload, ensure_ascii=False))


async def process_excel_stream(query: str, file_ids: List[UUID], thread_id: Optional[UUID], user_id: UUID, db: AsyncSession) -> AsyncGenerator[ServerSentEvent, None]:
    """
    流式处理 Excel 数据，生成 SSE 事件，并保存到数据库

    统一响应格式:
    {
        "action": "load|analysis|generate|execute|done",
        "status": "start|done|error",
        "data": { ... }  // 可选
    }
    """
    errors = []
    turn_id: Optional[UUID] = None
    thread: Optional[Thread] = None
    turn: Optional[ThreadTurn] = None

    try:
        # ========== 创建或获取线程 ==========
        if thread_id:
            # 获取现有线程
            stmt = select(Thread).where(Thread.id == thread_id).where(Thread.user_id == user_id)
            result = await db.execute(stmt)
            thread = result.scalar_one_or_none()
            if not thread:
                yield sse("error", "error", {"message": "线程不存在或无权访问"})
                return
        else:
            # 创建新线程
            try:
                llm_client = get_llm_client()
                title = await asyncio.to_thread(generate_thread_title, query, llm_client)
            except Exception:
                title = query
            thread = Thread(
                id=uuid4(),
                user_id=user_id,
                title=title,  # 可以后续根据第一条消息自动生成
                status="active",
            )
            db.add(thread)
            await db.commit()
            thread_id = thread.id
            yield ServerSentEvent(data=json.dumps({ "action": "refresh:thread" }, ensure_ascii=False))

        # ========== 创建消息记录 ==========
        # 获取下一个 turn_number
        stmt = select(func.max(ThreadTurn.turn_number)).where(ThreadTurn.thread_id == thread_id)
        result = await db.execute(stmt)
        max_turn_number = result.scalar_one_or_none() or 0
        next_turn_number = max_turn_number + 1

        turn = ThreadTurn(
            id=uuid4(),
            thread_id=thread_id,
            turn_number=next_turn_number,
            user_query=query,
            status="pending",
        )
        db.add(turn)
        await db.flush()
        turn_id = turn.id

        # ========== 关联文件到消息 ==========
        for file_id in file_ids:
            # 验证文件权限
            stmt = select(File).where(File.id == file_id).where(File.user_id == user_id)
            result = await db.execute(stmt)
            file_record = result.scalar_one_or_none()
            if not file_record:
                yield sse("error", "error", {"message": f"文件不存在或无权访问: {file_id}"})
                return

            # 创建关联
            turn_file = TurnFile(
                id=uuid4(),
                turn_id=turn_id,
                file_id=file_id,
            )
            db.add(turn_file)

        await db.flush()

        # ========== 加载文件 ==========
        yield sse("load", "start")
        turn.status = "processing"
        turn.started_at = datetime.now(timezone.utc)
        await db.flush()

        try:
            files = await get_files_by_ids_from_db(db, file_ids, user_id)
        except HTTPException as e:
            turn.status = "failed"
            turn.error_message = f"加载文件失败: {e.detail}"
            await db.commit()
            yield sse("load", "error", {"message": e.detail})
            return

        if not files:
            turn.status = "failed"
            turn.error_message = "没有有效的 Excel 文件"
            await db.commit()
            yield sse("load", "error", {"message": "没有有效的 Excel 文件"})
            return

        try:
            tables = await asyncio.to_thread(load_tables_from_files, files)
            schemas = tables.get_schemas()
            yield sse("load", "done", {"schemas": schemas})
        except HTTPException as e:
            turn.status = "failed"
            turn.error_message = f"解析文件失败: {e.detail}"
            await db.commit()
            yield sse("load", "error", {"message": e.detail})
            return

        llm_client = get_llm_client()

        # ========== 需求分析 ==========
        yield sse("analysis", "start")

        try:
            analysis = await asyncio.to_thread(
                llm_client.analyze_requirement, query, schemas
            )
            turn.analysis = analysis
            await db.flush()
            yield sse("analysis", "done", {"content": analysis})
        except Exception as e:
            turn.status = "failed"
            turn.error_message = f"需求分析失败: {e}"
            await db.commit()
            yield sse("analysis", "error", {"message": f"需求分析失败: {e}"})
            return

        # ========== 生成操作 ==========
        yield sse("generate", "start")

        try:
            operations_json = await asyncio.to_thread(
                llm_client.generate_operations, query, analysis, schemas
            )
            operations_dict = json.loads(operations_json)
            turn.operations_json = operations_dict
            await db.flush()
            yield sse("generate", "done", {"content": operations_dict})
        except json.JSONDecodeError:
            turn.status = "failed"
            turn.error_message = "LLM 生成的 JSON 格式错误"
            await db.commit()
            yield sse("generate", "error", {"message": "LLM 生成的 JSON 格式错误"})
            return
        except Exception as e:
            turn.status = "failed"
            turn.error_message = f"生成操作失败: {e}"
            await db.commit()
            yield sse("generate", "error", {"message": f"生成操作失败: {e}"})
            return

        # 解析验证
        operations, parse_errors = parse_and_validate(
            operations_json, tables.get_table_names()
        )
        if parse_errors:
            errors.extend(parse_errors)

        # ========== 执行操作 ==========
        yield sse("execute", "start")

        new_columns = {}
        output_file = None
        output_file_path = None
        execution_result = None

        if operations and not parse_errors:
            try:
                execution_result = await asyncio.to_thread(execute_operations, operations, tables)

                # 新列只返回前 10 行预览
                for table_name, cols in execution_result.new_columns.items():
                    new_columns[table_name] = {
                        col: values[:10] for col, values in cols.items()
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
        formulas = None
        if operations:
            try:
                excel_formulas = await asyncio.to_thread(generate_formulas, operations, tables)
                formulas = format_formula_output(excel_formulas)
            except Exception:
                pass

        # ========== 保存处理结果 ==========
        # 准备变量数据（从执行结果中提取）
        variables = {}
        if execution_result:
            variables = execution_result.variables

        # 创建结果记录
        turn_result = TurnResult(
            id=uuid4(),
            turn_id=turn_id,
            variables=variables if variables else None,
            new_columns=new_columns if new_columns else None,
            formulas=formulas,
            output_file=output_file,
            output_file_path=output_file_path,
            errors=errors if errors else None,
        )
        db.add(turn_result)

        # 更新消息状态
        if errors:
            turn.status = "failed"
            turn.error_message = "; ".join(errors[:3])  # 只保存前3个错误
        else:
            turn.status = "completed"
        turn.completed_at = datetime.now(timezone.utc)

        # 更新线程更新时间
        thread.updated_at = datetime.now(timezone.utc)

        await db.commit()

        yield sse("execute", "done", {
            "output_file": output_file_path or output_file,
            "formulas": formulas,
            "turn_id": str(turn_id),
            "thread_id": str(thread_id),
        })

    except Exception as e:
        await db.rollback()
        if turn:
            try:
                turn.status = "failed"
                turn.error_message = str(e)
                await db.commit()
            except:
                pass
        yield sse("error", "error", {"message": f"处理失败: {e}"})


class ChatRequest(BaseModel):
    """Excel 处理请求"""
    query: str = Field(..., description="数据处理需求的自然语言描述")
    file_ids: List[str] = Field(..., description="上传文件返回的 file_id 列表（UUID 字符串），支持多个文件")
    thread_id: Optional[str] = Field(None, description="线程 ID（可选，用于继续会话）")


@router.post("/excel/chat", summary="处理 Excel 需求", description="使用自然语言描述数据处理需求，LLM 会自动理解并执行相应操作。")
async def process_excel_chat(params: ChatRequest, current_user: User = Depends(get_current_user)):
    """
    使用 LLM 智能处理 Excel 数据（SSE 流式响应），保存到数据库

    响应格式:
    ```json
    {
        "action": "load|analysis|generate|execute",
        "status": "start|done|error",
        "data": {...}
    }
    ```

    - load: 加载文件
    - analysis: 需求分析
    - generate: 生成操作
    - execute: 执行操作

    流程:
    1. load: start → done(schemas) / error
    2. analysis: start → done(content) / error
    3. generate: start → done(content) / error
    4. execute: start → done(output_file, formulas, turn_id, thread_id)
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
                yield sse("error", "error", {"message": f"处理失败: {error}"})
            finally:
                await db.close()

    return EventSourceResponse(stream_with_db())


# ========== 线程管理 API ==========

class ThreadListItem(BaseModel):
    """线程列表项"""
    id: str
    title: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime
    turn_count: int = Field(default=0, description="消息数量")


class ThreadDetail(BaseModel):
    """线程详情"""
    id: str
    title: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime
    turns: List[dict] = Field(default_factory=list, description="消息列表")


@router.get("/threads", response_model=ApiResponse[List[ThreadListItem]], summary="获取线程列表", description="获取当前用户的所有线程列表")
async def get_threads(limit: int = 50, offset: int = 0, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """获取用户的线程列表"""
    try:
        # 查询线程，按更新时间倒序
        stmt = (
            select(Thread, func.count(ThreadTurn.id).label("turn_count"))
            .outerjoin(ThreadTurn, Thread.id == ThreadTurn.thread_id)
            .where(Thread.user_id == current_user.id)
            .where(Thread.status == "active")
            .group_by(Thread.id)
            .order_by(Thread.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await db.execute(stmt)
        rows = result.all()

        threads = []
        for thread, turn_count in rows:
            threads.append(ThreadListItem(
                id=str(thread.id),
                title=thread.title,
                status=thread.status,
                created_at=thread.created_at,
                updated_at=thread.updated_at,
                turn_count=turn_count or 0,
            ))

        return ApiResponse(
            code=0,
            data=threads,
            msg="获取成功"
        )
    except Exception as e:
        return ApiResponse(
            code=500,
            data=None,
            msg=f"获取失败: {str(e)}"
        )


@router.get("/threads/{thread_id}", response_model=ApiResponse[ThreadDetail], summary="获取线程详情", description="获取指定线程的详细信息，包含所有消息")
async def get_thread_detail(thread_id: str, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """获取线程详情"""
    try:
        # 转换 thread_id 为 UUID
        try:
            thread_id_uuid = UUID(thread_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="无效的 thread_id 格式")

        # 查询线程
        stmt = select(Thread).where(Thread.id == thread_id_uuid).where(Thread.user_id == current_user.id)
        result = await db.execute(stmt)
        thread = result.scalar_one_or_none()

        if not thread:
            raise HTTPException(status_code=404, detail="线程不存在或无权访问")

        # 查询消息列表，预加载关联的关系
        turns_stmt = (
            select(ThreadTurn)
            .options(
                selectinload(ThreadTurn.files),
                selectinload(ThreadTurn.result)
            )
            .where(ThreadTurn.thread_id == thread_id_uuid)
            .order_by(ThreadTurn.turn_number.asc())
        )
        turns_result = await db.execute(turns_stmt)
        turns = turns_result.scalars().all()

        # 构建消息列表
        turns_data = []
        for turn in turns:
            turn_data = {
                "id": str(turn.id),
                "turn_number": turn.turn_number,
                "user_query": turn.user_query,
                "status": turn.status,
                "analysis": turn.analysis,
                "operations_json": turn.operations_json,
                "error_message": turn.error_message,
                "created_at": turn.created_at.isoformat(),
                "completed_at": turn.completed_at.isoformat() if turn.completed_at else None,
            }

            # 获取关联的文件
            if turn.files:
                files_data = []
                for f in turn.files:
                    # 构造可访问的文件 URL（与静态目录挂载保持一致）
                    file_url = "/" + f.file_path.lstrip("/")
                    files_data.append({
                        "id": str(f.id),
                        "filename": f.filename,
                        "path": file_url,
                        "size": f.file_size,
                        "mime_type": f.mime_type,
                        "uploaded_at": f.uploaded_at.isoformat(),
                    })

                # 保持向后兼容的同时，提供完整文件信息
                turn_data["file_ids"] = [file["id"] for file in files_data]
                turn_data["files"] = files_data

            # 获取结果
            if turn.result:
                turn_data["result"] = {
                    "output_file": turn.result.output_file,
                    "output_file_path": turn.result.output_file_path,
                    "formulas": turn.result.formulas,
                }

            turns_data.append(turn_data)

        return ApiResponse(
            code=0,
            data=ThreadDetail(
                id=str(thread.id),
                title=thread.title,
                status=thread.status,
                created_at=thread.created_at,
                updated_at=thread.updated_at,
                turns=turns_data,
            ),
            msg="获取成功"
        )
    except HTTPException:
        raise
    except Exception as e:
        return ApiResponse(
            code=500,
            data=None,
            msg=f"获取失败: {str(e)}"
        )


@router.delete("/threads/{thread_id}", response_model=ApiResponse[None], summary="删除线程", description="删除指定的线程")
async def delete_thread(thread_id: str, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """删除线程"""
    try:
        # 转换 thread_id 为 UUID
        try:
            thread_id_uuid = UUID(thread_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="无效的 thread_id 格式")

        # 查询线程
        stmt = select(Thread).where(Thread.id == thread_id_uuid).where(Thread.user_id == current_user.id)
        result = await db.execute(stmt)
        thread = result.scalar_one_or_none()

        if not thread:
            raise HTTPException(status_code=404, detail="线程不存在或无权访问")

        # 软删除：更新状态
        thread.status = "deleted"
        await db.commit()

        return ApiResponse(
            code=0,
            data=None,
            msg="删除成功"
        )
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        return ApiResponse(
            code=500,
            data=None,
            msg=f"删除失败: {str(e)}"
        )


