"""Excel 处理服务"""

import json
import uuid
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Optional
from dataclasses import dataclass
from uuid import UUID

from fastapi import UploadFile, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.models import TableCollection
from app.core.excel_parser import ExcelParser
from app.core.llm_client import LLMClient
from app.core.executor import execute_operations
from app.core.excel_generator import generate_formulas
from app.core.parser import parse_and_validate
from app.core.config import UPLOAD_DIR, OUTPUT_DIR
from app.models.file import File


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


def load_tables_from_files(files: List[File]) -> TableCollection:
    """从文件记录加载表（内部通过 ExcelParser 使用 MinIO 解析）"""
    # 将数据库记录转换为 (MinIO 公共路径, 原始文件名) 形式，传给解析器
    file_infos = []
    for f in files:
        file_infos.append((f.file_path, f.filename or Path(f.file_path).name))

    try:
        return ExcelParser.load_tables_from_minio_paths(file_infos)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"解析文件失败: {e}")


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


async def save_file_to_database(
    db: AsyncSession,
    user_id: UUID,
    file: UploadFile,
    file_path: Path,
) -> File:
    """
    保存文件到数据库（计算 MD5，检查重复，关联用户）

    Args:
        db: 数据库会话
        user_id: 用户 ID
        file: 上传的文件
        file_path: 文件保存路径

    Returns:
        File 对象（如果文件已存在，返回已存在的文件）
    """
    # 读取文件内容并计算 MD5
    content = await file.read()
    await file.seek(0)  # 重置文件指针，以便后续使用
    
    md5_hash = hashlib.md5(content).hexdigest()
    file_size = len(content)
    mime_type = file.content_type or "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    # 检查文件是否已存在（通过 MD5）
    # stmt = select(File).where(File.md5 == md5_hash)
    # result = await db.execute(stmt)
    # existing_file = result.scalar_one_or_none()

    # if existing_file:
    #     # 文件已存在，检查是否属于当前用户
    #     if existing_file.user_id == user_id:
    #         # 属于当前用户，直接返回
    #         return existing_file
    #     else:
    #         # 文件存在但属于其他用户，创建新的文件记录（共享文件存储，但记录不同）
    #         # 注意：这里我们仍然创建新记录，但可以共享文件存储路径
    #         # 或者可以选择创建硬链接/符号链接来节省空间
    #         pass

    # 创建新的文件记录
    file_id = uuid.uuid4()
    # 保存相对路径（相对于项目根目录）
    try:
        # 尝试转换为相对路径
        relative_path = file_path.relative_to(Path.cwd())
        file_path_str = str(relative_path)
    except ValueError:
        # 如果无法转换为相对路径，使用绝对路径
        file_path_str = str(file_path)
    
    file_record = File(
        id=file_id,
        user_id=user_id,
        filename=file.filename or "unknown.xlsx",
        file_path=file_path_str,
        file_size=file_size,
        md5=md5_hash,
        mime_type=mime_type,
        uploaded_at=datetime.now(timezone.utc),
    )
    
    db.add(file_record)

    return file_record


async def get_file_by_id_from_db(db: AsyncSession, file_id: UUID, user_id: UUID) -> File:
    """
    从数据库获取文件（验证用户权限）

    Args:
        db: 数据库会话
        file_id: 文件 ID
        user_id: 用户 ID（用于权限验证）

    Returns:
        File 对象

    Raises:
        HTTPException: 文件不存在或无权访问
    """
    stmt = select(File).where(File.id == file_id)
    result = await db.execute(stmt)
    file_record = result.scalar_one_or_none()

    if not file_record:
        raise HTTPException(status_code=404, detail=f"文件不存在: {file_id}")

    # 验证用户权限（只能访问自己的文件）
    if file_record.user_id != user_id:
        raise HTTPException(status_code=403, detail="无权访问该文件")

    return file_record


def get_file_path_from_db(file_record: File) -> Path:
    """
    从数据库记录获取文件路径

    Args:
        file_record: File 对象

    Returns:
        文件路径（当前为 MinIO 公共访问路径或本地相对路径）
    """
    # 历史原因：之前是本地文件系统路径，这里保留相对路径 → 绝对路径的处理，
    # 但不再强制要求本地存在，以便兼容 MinIO 等远程存储。
    file_path = Path(file_record.file_path)
    if not file_path.is_absolute():
        # 相对路径是相对于项目根目录的
        file_path = Path.cwd() / file_path

    return file_path


def get_files_by_id(file_id: str) -> List[Path]:
    """根据 file_id 获取文件路径（旧版本兼容，已废弃）"""
    file_dir = UPLOAD_DIR / file_id
    if not file_dir.exists():
        raise HTTPException(status_code=404, detail=f"file_id 不存在: {file_id}")

    # 每个目录下只有一个文件，获取该文件
    files = list(file_dir.glob("*.xlsx")) + list(file_dir.glob("*.xls"))
    if not files:
        raise HTTPException(status_code=404, detail=f"file_id 对应的文件不存在: {file_id}")

    return files


async def get_files_by_ids_from_db(
    db: AsyncSession,
    file_ids: List[UUID],
    user_id: UUID,
) -> List[File]:
    """
    从数据库获取多个文件路径（验证用户权限）

    Args:
        db: 数据库会话
        file_ids: 文件 ID 列表
        user_id: 用户 ID（用于权限验证）

    Returns:
        文件记录列表
    """
    files: List[File] = []
    for file_id in file_ids:
        file_record = await get_file_by_id_from_db(db, file_id, user_id)
        files.append(file_record)

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
