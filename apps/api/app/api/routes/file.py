"""通用文件上传到 MinIO 的接口"""
import io
from typing import List
from uuid import uuid4, UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from minio import Minio
from minio.error import S3Error

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.models import File
from app.models.user import User
from app.schemas.response import ApiResponse

router = APIRouter(prefix="/file", tags=["文件"])


class FileItem(BaseModel):
    id: str
    filename: str
    path: str
    content_type: str | None = None


def get_minio_client() -> Minio:

    return Minio(
        endpoint=settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=False,
    )

@router.post("/upload", response_model=ApiResponse[List[FileItem]], summary="文件上传")
async def upload_file(files: List[UploadFile], current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """文件上传接口：将文件存储到 MinIO"""
    if not files or len(files) == 0:
        return ApiResponse(code=400, data=None, msg="请上传文件")

    try:
        client = get_minio_client()
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )

    bucket_name = settings.MINIO_BUCKET

    # 确保桶存在
    try:
        if not client.bucket_exists(bucket_name):
            client.make_bucket(bucket_name)
    except S3Error as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"初始化 MinIO 存储桶失败: {e}",
        )

    items: List[FileItem] = []

    for file in files:
        # 读取文件内容到内存（如果后续有大文件需求可以改成流式上传）
        content = await file.read()
        size = len(content)

        # 使用 uuid 防止文件名冲突，保留原始扩展名
        ext = ""
        if "." in file.filename:
            ext = "." + file.filename.rsplit(".", 1)[-1]
        file_id = uuid4().hex
        object_name = f"uploads/{current_user.id}/{file_id}{ext}"

        try:
            client.put_object(
                bucket_name=bucket_name,
                object_name=object_name,
                data=io.BytesIO(content),
                length=size,
                content_type=file.content_type or "application/octet-stream",
            )
            public_url = f"/{settings.MINIO_PUBLIC_BASE.rstrip('/')}/{bucket_name}/{object_name}"

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
        except S3Error as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"上传文件到 MinIO 失败: {e}",
            )



    return ApiResponse(
        code=0,
        data=items,
        msg="上传成功",
    )
