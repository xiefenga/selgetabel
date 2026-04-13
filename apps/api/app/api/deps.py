"""API 依赖"""

from typing import Optional, List, Union
from uuid import UUID

from fastapi import HTTPException, Depends, Request, Response, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.services.llm_config import load_stage_configs, LLMConfigError
from app.core.database import AsyncSessionLocal
from app.core.database import get_db
from app.core.jwt import verify_token, create_access_token
from app.core.config import settings
from app.services.auth import (
    get_user_by_id,
    get_refresh_token,
    get_user_roles,
)
from app.models.user import User
from app.models.role import Permission

# HTTP Bearer Token 认证（作为备用方案，优先使用 cookie）
security = HTTPBearer(auto_error=False)


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


# ==================== 权限系统 ====================


async def get_user_permissions(user: User, db: AsyncSession) -> List[str]:
    """
    获取用户的所有权限

    Args:
        user: 用户对象
        db: 数据库会话

    Returns:
        用户权限代码列表
    """
    permissions = set()

    # 重新查询用户，预加载角色和权限
    from app.models.role import Role

    stmt = (
        select(User)
        .options(
            selectinload(User.roles).selectinload(Role.permissions)
        )
        .where(User.id == user.id)
    )
    result = await db.execute(stmt)
    user_with_relations = result.scalar_one_or_none()

    if not user_with_relations:
        return []

    # 通过用户的角色获取权限
    for role in user_with_relations.roles:
        for permission in role.permissions:
            permissions.add(permission.code)

    return list(permissions)


def _match_permission_pattern(pattern: List[str], target: List[str]) -> bool:
    """
    匹配权限通配符模式

    Args:
        pattern: 权限模式（可能包含通配符 *）
        target: 目标权限

    Returns:
        是否匹配
    """
    if len(pattern) != len(target):
        return False

    for p, t in zip(pattern, target):
        if p != "*" and p != t:
            return False

    return True


def check_permission(
    required_permission: Union[str, List[str]],
    match_all: bool = False
):
    """
    检查权限的依赖注入函数

    Args:
        required_permission: 必需的权限代码或权限代码列表
        match_all: 如果为 True，需要匹配所有权限；否则匹配任意一个即可

    Returns:
        依赖函数

    Raises:
        HTTPException: 权限不足时抛出 403
    """
    async def _check_permission(
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
    ) -> User:
        # 获取用户权限
        user_permissions = await get_user_permissions(user, db)

        # 检查超级权限
        if "*:*" in user_permissions:
            return user

        # 标准化为列表
        required_permissions = (
            required_permission if isinstance(required_permission, list)
            else [required_permission]
        )

        # 检查通配符权限
        matched_permissions = set()
        for user_perm in user_permissions:
            if "*" in user_perm:
                # 解析通配符权限
                pattern_parts = user_perm.split(":")
                for req_perm in required_permissions:
                    req_parts = req_perm.split(":")
                    # 模式匹配
                    if _match_permission_pattern(pattern_parts, req_parts):
                        matched_permissions.add(req_perm)

        # 精确匹配
        for req_perm in required_permissions:
            if req_perm in user_permissions:
                matched_permissions.add(req_perm)

        # 判断是否满足权限要求
        if match_all:
            # 需要匹配所有权限
            if len(matched_permissions) >= len(required_permissions):
                return user
        else:
            # 匹配任意一个权限即可
            if len(matched_permissions) > 0:
                return user

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足"
        )

    return _check_permission


async def has_permission(
    user: User,
    db: AsyncSession,
    required_permission: Union[str, List[str]],
    match_all: bool = False
) -> bool:
    """
    检查用户是否拥有指定权限（用于业务逻辑中的权限判断）

    Args:
        user: 用户对象
        db: 数据库会话
        required_permission: 必需的权限代码或权限代码列表
        match_all: 如果为 True，需要匹配所有权限；否则匹配任意一个即可

    Returns:
        是否拥有权限
    """
    user_permissions = await get_user_permissions(user, db)

    # 检查超级权限
    if "*:*" in user_permissions:
        return True

    # 标准化为列表
    required_permissions = (
        required_permission if isinstance(required_permission, list)
        else [required_permission]
    )

    # 检查通配符权限
    matched_permissions = set()
    for user_perm in user_permissions:
        if "*" in user_perm:
            pattern_parts = user_perm.split(":")
            for req_perm in required_permissions:
                req_parts = req_perm.split(":")
                if _match_permission_pattern(pattern_parts, req_parts):
                    matched_permissions.add(req_perm)

    # 精确匹配
    for req_perm in required_permissions:
        if req_perm in user_permissions:
            matched_permissions.add(req_perm)

    # 判断是否满足权限要求
    if match_all:
        return len(matched_permissions) >= len(required_permissions)
    else:
        return len(matched_permissions) > 0
