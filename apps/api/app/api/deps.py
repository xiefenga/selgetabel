"""API 依赖"""

from typing import Optional
from uuid import UUID

from fastapi import HTTPException, Depends, Request, Response, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.llm_client import LLMClient
from app.core.database import get_db
from app.core.jwt import verify_token, create_access_token
from app.core.config import settings
from app.services.auth import (
    get_user_by_id,
    get_refresh_token,
    get_user_roles,
)
from app.models.user import User

# HTTP Bearer Token 认证（作为备用方案，优先使用 cookie）
security = HTTPBearer(auto_error=False)


def get_llm_client() -> LLMClient:
    """获取 LLM 客户端"""
    try:
        return LLMClient()
    except ValueError as e:
        raise HTTPException(status_code=500, detail=f"LLM 初始化失败: {e}")


async def get_current_user(
    request: Request,
    response: Response,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    获取当前登录用户（优先从 cookie 读取，备用从 Authorization header）。

    为了实现“无感刷新”：
    - 优先尝试使用 access_token 验证；
    - 如果 access_token 不可用，则尝试使用 refresh_token 刷新并下发新的 access_token，
      同时本次请求仍视为已登录。
    """
    access_token: Optional[str] = None

    # 优先从 cookie 读取 access_token
    access_token = request.cookies.get("access_token")

    # 如果 cookie 中没有 access_token，尝试从 Authorization header 读取（向后兼容）
    if not access_token and credentials:
        access_token = credentials.credentials

    user: Optional[User] = None

    # 1. 尝试使用 access_token 直接认证
    if access_token:
        payload = verify_token(access_token, token_type="access")
        if payload:
            user_id = payload.get("sub")
            if not user_id:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="令牌格式错误",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            try:
                user_id_uuid = UUID(user_id)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="无效的用户 ID",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            user = await get_user_by_id(db, user_id_uuid)
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="用户不存在或已被禁用",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            # access_token 有效，直接返回
            return user

    # 2. access_token 不可用，尝试使用 refresh_token 进行无感刷新
    refresh_token_str = request.cookies.get("refresh_token")
    if refresh_token_str:
        refresh_payload = verify_token(refresh_token_str, token_type="refresh")
        if refresh_payload:
            # 检查数据库中的刷新令牌记录是否仍然有效
            refresh_token_record = await get_refresh_token(db, refresh_token_str)
            if refresh_token_record:
                user_id = refresh_payload.get("sub")
                try:
                    user_id_uuid = UUID(user_id)
                except (TypeError, ValueError):
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="无效的用户 ID",
                        headers={"WWW-Authenticate": "Bearer"},
                    )

                user = await get_user_by_id(db, user_id_uuid)
                if not user:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="用户不存在或已被禁用",
                        headers={"WWW-Authenticate": "Bearer"},
                    )

                # 基于当前用户角色生成新的 access_token，并通过 cookie 下发
                roles = await get_user_roles(db, user.id)
                new_access_token = create_access_token(
                    user_id=user.id,
                    username=user.username,
                    roles=roles,
                )

                access_token_max_age = settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60
                response.set_cookie(
                    key="access_token",
                    value=new_access_token,
                    max_age=access_token_max_age,
                    httponly=True,
                    secure=False,  # 生产环境应设置为 True（HTTPS）
                    samesite="lax",
                )

                # 本次请求直接视为已登录
                return user

    # 3. 无法通过 access_token 或 refresh_token 完成认证，返回未登录
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="未提供有效的访问令牌",
        headers={"WWW-Authenticate": "Bearer"},
    )
