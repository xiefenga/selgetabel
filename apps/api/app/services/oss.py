"""OSS (MinIO) 存储服务"""
import io
from typing import Union, BinaryIO
from uuid import uuid4

from minio import Minio
from minio.error import S3Error

from app.core.config import settings


class OSSError(Exception):
    """OSS 操作异常"""
    pass


def get_minio_client() -> Minio:
    """获取 MinIO 客户端"""
    return Minio(
        endpoint=settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=False,
    )


def ensure_bucket_exists(client: Minio, bucket_name: str) -> None:
    """确保存储桶存在，不存在则创建"""
    try:
        if not client.bucket_exists(bucket_name):
            client.make_bucket(bucket_name)
    except S3Error as e:
        raise OSSError(f"初始化 MinIO 存储桶失败: {e}")


def generate_object_name(
    user_id: str,
    file_id: str | None = None,
    ext: str = "",
    prefix: str = "uploads"
) -> str:
    """
    生成 OSS 对象名称

    Args:
        user_id: 用户 ID
        file_id: 文件 ID（可选，不提供则自动生成）
        ext: 文件扩展名（如 ".xlsx"）
        prefix: 路径前缀（"uploads" 或 "outputs"）

    Returns:
        对象名称，如 "uploads/{user_id}/{file_id}.xlsx"
    """
    if file_id is None:
        file_id = uuid4().hex
    return f"{prefix}/{user_id}/{file_id}{ext}"


def generate_public_url(bucket_name: str, object_name: str) -> str:
    """
    生成文件的公共访问 URL

    Args:
        bucket_name: 存储桶名称
        object_name: 对象名称

    Returns:
        公共访问 URL
    """
    return f"/{settings.MINIO_PUBLIC_BASE.rstrip('/')}/{bucket_name}/{object_name}"


def upload_file(
    data: Union[bytes, BinaryIO],
    object_name: str,
    content_type: str = "application/octet-stream",
    size: int | None = None,
) -> str:
    """
    上传文件到 OSS

    Args:
        data: 文件内容（bytes 或文件对象）
        object_name: 对象名称（完整路径）
        content_type: 内容类型
        size: 文件大小（如果 data 是 bytes 可自动计算）

    Returns:
        公共访问 URL

    Raises:
        OSSError: 上传失败时抛出
    """
    client = get_minio_client()
    bucket_name = settings.MINIO_BUCKET

    # 确保桶存在
    ensure_bucket_exists(client, bucket_name)

    # 处理数据
    if isinstance(data, bytes):
        size = len(data)
        data = io.BytesIO(data)
    elif size is None:
        raise OSSError("当 data 不是 bytes 时，必须提供 size 参数")

    try:
        client.put_object(
            bucket_name=bucket_name,
            object_name=object_name,
            data=data,
            length=size,
            content_type=content_type,
        )
        return generate_public_url(bucket_name, object_name)
    except S3Error as e:
        raise OSSError(f"上传文件到 MinIO 失败: {e}")


def upload_user_file(
    data: Union[bytes, BinaryIO],
    user_id: str,
    filename: str,
    content_type: str = "application/octet-stream",
    size: int | None = None,
    prefix: str = "uploads",
) -> tuple[str, str, str]:
    """
    上传用户文件到 OSS（便捷方法）

    Args:
        data: 文件内容
        user_id: 用户 ID
        filename: 原始文件名（用于提取扩展名）
        content_type: 内容类型
        size: 文件大小
        prefix: 路径前缀（"uploads" 或 "outputs"）

    Returns:
        (file_id, object_name, public_url) 元组

    Raises:
        OSSError: 上传失败时抛出
    """
    # 提取扩展名
    ext = ""
    if "." in filename:
        ext = "." + filename.rsplit(".", 1)[-1]

    # 生成文件 ID 和对象名称
    file_id = uuid4().hex
    object_name = generate_object_name(user_id, file_id, ext, prefix)

    # 上传文件
    public_url = upload_file(data, object_name, content_type, size)

    return file_id, object_name, public_url
