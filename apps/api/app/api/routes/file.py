"""通用文件上传到 MinIO 的接口"""
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import File
from app.models.user import User
from app.schemas.response import ApiResponse
from app.services.oss import upload_user_file, OSSError

router = APIRouter(prefix="/file", tags=["文件"])


class FileItem(BaseModel):
    id: str
    filename: str
    path: str
    content_type: str | None = None

@router.post("/upload", response_model=ApiResponse[List[FileItem]], summary="文件上传")
async def upload_file(files: List[UploadFile], current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """文件上传接口：将文件存储到 MinIO"""
    if not files or len(files) == 0:
        return ApiResponse(code=400, data=None, msg="请上传文件")

    items: List[FileItem] = []

    for file in files:
        # 读取文件内容到内存（如果后续有大文件需求可以改成流式上传）
        content = await file.read()
        size = len(content)

        try:
            # 使用公共 OSS 服务上传文件
            file_id, object_name, public_url = upload_user_file(
                data=content,
                user_id=str(current_user.id),
                filename=file.filename,
                content_type=file.content_type or "application/octet-stream",
                size=size,
                prefix="uploads",
            )

            file_record = File(
                id=UUID(file_id),
                user_id=current_user.id,
                filename=file.filename,
                file_path=public_url,
                file_size=file.size,
                md5="",
                mime_type=file.content_type,
            )

            db.add(file_record)

            items.append(
                FileItem(
                    id=file_record.id.hex,
                    path=public_url,
                    filename=file.filename,
                    content_type=file.content_type,
                )
            )
        except OSSError as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(e),
            )

    return ApiResponse(
        code=0,
        data=items,
        msg="上传成功",
    )
