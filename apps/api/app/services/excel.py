"""Excel 处理服务"""

import json
import uuid
from pathlib import Path
from datetime import datetime
from typing import List, Optional
from dataclasses import dataclass

from fastapi import UploadFile, HTTPException

from app.core.models import TableCollection
from app.core.excel_parser import ExcelParser
from app.core.llm_client import LLMClient
from app.core.executor import execute_operations
from app.core.excel_generator import generate_formulas
from app.core.parser import parse_and_validate
from app.core.config import UPLOAD_DIR, OUTPUT_DIR


@dataclass
class ProcessResult:
    """处理结果"""
    analysis: str
    operations: dict
    variables: dict
    new_columns: dict
    excel_formulas: list
    output_file: Optional[str]
    errors: list


def load_tables_from_files(file_paths: List[Path]) -> TableCollection:
    """从文件路径加载表"""
    tables = TableCollection()

    for file_path in file_paths:
        if not file_path.exists():
            raise HTTPException(status_code=404, detail=f"文件不存在: {file_path}")

        try:
            file_info = ExcelParser.get_file_info(file_path)

            if len(file_info['sheets']) > 1:
                sheet_tables = ExcelParser.parse_file_all_sheets(file_path)
                for table_name in sheet_tables.get_table_names():
                    tables.add_table(sheet_tables.get_table(table_name))
            else:
                table = ExcelParser.parse_file(file_path)
                tables.add_table(table)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"解析文件失败: {e}")

    return tables


async def save_upload_file(file: UploadFile, file_id: Optional[str] = None) -> tuple[str, Path]:
    """
    保存上传的文件（一个文件对应一个 id）

    Args:
        file: 上传的文件
        file_id: 可选的 file_id，如果不提供则生成完整的 UUID v4

    Returns:
        (file_id, saved_file_path)
    """
    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(status_code=400, detail="只能上传 Excel 文件 (.xlsx, .xls)")

    if file_id is None:
        file_id = str(uuid.uuid4())

    file_dir = UPLOAD_DIR / file_id
    file_dir.mkdir(parents=True, exist_ok=True)

    # 使用原始文件名
    file_path = file_dir / file.filename
    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    return file_id, file_path


def get_files_by_id(file_id: str) -> List[Path]:
    """根据 file_id 获取文件路径"""
    file_dir = UPLOAD_DIR / file_id
    if not file_dir.exists():
        raise HTTPException(status_code=404, detail=f"file_id 不存在: {file_id}")

    # 每个目录下只有一个文件，获取该文件
    files = list(file_dir.glob("*.xlsx")) + list(file_dir.glob("*.xls"))
    if not files:
        raise HTTPException(status_code=404, detail=f"file_id 对应的文件不存在: {file_id}")

    return files


def process_excel(
    query: str,
    tables: TableCollection,
    llm_client: LLMClient,
) -> ProcessResult:
    """
    处理 Excel 数据

    Args:
        query: 用户需求
        tables: 表集合
        llm_client: LLM 客户端

    Returns:
        ProcessResult
    """
    schemas = tables.get_schemas()
    errors = []

    # ========== 第一步：需求分析 ==========
    try:
        analysis = llm_client.analyze_requirement(query, schemas)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"需求分析失败: {e}")

    # ========== 第二步：生成操作 ==========
    try:
        operations_json = llm_client.generate_operations(query, analysis, schemas)
        operations_dict = json.loads(operations_json)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="LLM 生成的 JSON 格式错误")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成操作失败: {e}")

    # 解析验证
    operations, parse_errors = parse_and_validate(
        operations_json, tables.get_table_names()
    )
    if parse_errors:
        errors.extend(parse_errors)

    # ========== 第三步：执行 ==========
    variables = {}
    new_columns = {}
    output_file = None

    if operations and not parse_errors:
        try:
            result = execute_operations(operations, tables)
            variables = result.variables

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
                tables.export_to_excel(str(output_path))
                output_file = output_filename

        except Exception as e:
            errors.append(f"执行失败: {e}")

    # ========== 第四步：生成公式 ==========
    excel_formulas = []
    if operations:
        try:
            excel_formulas = generate_formulas(operations, tables)
        except Exception:
            pass

    return ProcessResult(
        analysis=analysis,
        operations=operations_dict,
        variables=variables,
        new_columns=new_columns,
        excel_formulas=excel_formulas,
        output_file=output_file,
        errors=errors,
    )
