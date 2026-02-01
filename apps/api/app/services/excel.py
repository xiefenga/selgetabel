"""Excel 处理服务"""
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

from app.engine.models import FileCollection
from app.engine.excel_parser import ExcelParser
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


def load_tables_from_files(files: List[File]) -> FileCollection:
    """从文件记录加载表（内部通过 ExcelParser 使用 MinIO 解析）"""
    # 将数据库记录转换为 (file_id, file_path, filename) 形式，传给解析器
    file_records = []
    for f in files:
        file_records.append((
            str(f.id),  # file_id
            f.file_path,  # MinIO 公共路径
            f.filename or Path(f.file_path).name  # 原始文件名
        ))

    try:
        return ExcelParser.load_tables_from_minio_paths(file_records)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"解析文件失败: {e}")




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


