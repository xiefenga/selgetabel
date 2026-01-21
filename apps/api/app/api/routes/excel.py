import json
import asyncio
from typing import List, AsyncGenerator
from datetime import datetime

from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse, ServerSentEvent


from app.schemas.response import UploadItem, ApiResponse
from app.api.deps import get_llm_client
from app.services.excel import (
    load_tables_from_files,
    save_upload_file,
    get_files_by_id,
)
from app.core.parser import parse_and_validate
from app.core.executor import execute_operations
from app.core.excel_generator import generate_formulas, format_formula_output
from app.core.config import OUTPUT_DIR

router = APIRouter()

@router.post("/excel/upload", response_model=ApiResponse[List[UploadItem]], summary="上传 Excel 文件", description="上传一个或多个 Excel 文件，系统会自动解析表结构。每个文件会获得独立的 file_id。")
async def upload_excel_files(files: List[UploadFile] = File(...)):
    """上传 Excel 文件，每个文件对应一个独立的 file_id"""
    if not files:
        return ApiResponse(
            code=400,
            data=None,
            msg="请上传文件"
        )

    # 为每个文件生成独立的 id 并加载表结构
    items: List[UploadItem] = []
    file_ids = []

    for file in files:
        try:
            file_id, file_path = await save_upload_file(file)
            file_ids.append(file_id)

            # 为每个文件单独加载表结构
            file_tables = load_tables_from_files([file_path])
            schemas = file_tables.get_schemas()

            # 为每个表创建一个 UploadItem
            for table_name, table_schema in schemas.items():
                items.append(UploadItem(
                    id=file_id,
                    table=table_name,
                    schema=table_schema,
                    path=f"/{str(file_path)}",
                ))
        except HTTPException as e:
            # 跳过无效文件
            continue

    if not items:
        return ApiResponse(
            code=400,
            data=None,
            msg="没有有效的 Excel 文件"
        )

    return ApiResponse(
        code=0,
        data=items,
        msg="上传成功"
    )


def sse(action: str, status: str, data: dict = None) -> ServerSentEvent:
    """生成统一格式的 SSE 事件"""
    payload = {"action": action, "status": status}
    if data is not None:
        payload["data"] = data
    return ServerSentEvent(data=json.dumps(payload, ensure_ascii=False))


async def process_excel_stream(query: str, file_ids: List[str]) -> AsyncGenerator[ServerSentEvent, None]:
    """
    流式处理 Excel 数据，生成 SSE 事件

    统一响应格式:
    {
        "action": "load|analysis|generate|execute|done",
        "status": "start|done|error",
        "data": { ... }  // 可选
    }
    """
    errors = []

    # ========== 加载文件 ==========
    yield sse("load", "start")

    file_paths = []
    for file_id in file_ids:
        try:
            paths = get_files_by_id(file_id)
            file_paths.extend(paths)
        except HTTPException as e:
            yield sse("load", "error", {"message": f"file_id {file_id}: {e.detail}"})
            return

    if not file_paths:
        yield sse("load", "error", {"message": "没有有效的 Excel 文件"})
        return

    try:
        tables = await asyncio.to_thread(load_tables_from_files, file_paths)
        schemas = tables.get_schemas()
        yield sse("load", "done", {"schemas": schemas})
    except HTTPException as e:
        yield sse("load", "error", {"message": e.detail})
        return

    llm_client = get_llm_client()

    # ========== 需求分析 ==========
    yield sse("analysis", "start")

    try:
        analysis = await asyncio.to_thread(
            llm_client.analyze_requirement, query, schemas
        )
        yield sse("analysis", "done", {"content": analysis})
    except Exception as e:
        yield sse("analysis", "error", {"message": f"需求分析失败: {e}"})
        return

    # ========== 生成操作 ==========
    yield sse("generate", "start")

    try:
        operations_json = await asyncio.to_thread(
            llm_client.generate_operations, query, analysis, schemas
        )
        operations_dict = json.loads(operations_json)
        yield sse("generate", "done", {"content": operations_dict})
    except json.JSONDecodeError:
        yield sse("generate", "error", {"message": "LLM 生成的 JSON 格式错误"})
        return
    except Exception as e:
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

    if operations and not parse_errors:
        try:
            result = await asyncio.to_thread(execute_operations, operations, tables)

            # 新列只返回前 10 行预览
            for table_name, cols in result.new_columns.items():
                new_columns[table_name] = {
                    col: values[:10] for col, values in cols.items()
                }
            errors.extend(result.errors)

            # 导出文件
            if result.new_columns and not result.has_errors():
                tables.apply_new_columns(result.new_columns)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_filename = f"result_{timestamp}.xlsx"
                output_path = OUTPUT_DIR / output_filename
                await asyncio.to_thread(tables.export_to_excel, str(output_path))
                output_file = output_filename

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

    yield sse("execute", "done", {
        "output_file": str(output_path),
        "formulas": formulas,
    })


class ChatRequest(BaseModel):
    """Excel 处理请求"""
    query: str = Field(..., description="数据处理需求的自然语言描述")
    file_ids: List[str] = Field(..., description="上传文件返回的 file_id 列表，支持多个文件")


@router.post("/excel/chat", summary="处理 Excel 需求", description="使用自然语言描述数据处理需求，LLM 会自动理解并执行相应操作。")
async def process_excel_chat(request: ChatRequest):
    """
    使用 LLM 智能处理 Excel 数据（SSE 流式响应）

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
    4. execute: start → done(output_file, formulas)
    """
    return EventSourceResponse(process_excel_stream(request.query, request.file_ids))


