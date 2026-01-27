"""认证服务"""

from datetime import datetime, timedelta, timezone
from typing import Optional, List
from uuid import UUID, uuid4

import bcrypt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.user import User, Account
from app.models.auth import RefreshToken
from app.models.role import Role, Permission
from app.core.config import settings
from fastapi import HTTPException, status


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed_password.encode("utf-8"),
    )


def get_password_hash(password: str) -> str:
    """加密密码"""
    salt = bcrypt.gensalt(rounds=settings.BCRYPT_ROUNDS)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


async def get_user_by_account(db: AsyncSession, account_id: str, provider_id: str) -> Optional[User]:
    """通过账户标识获取用户"""
    stmt = (
        select(User)
        .join(Account)
        .where(Account.account_id == account_id)
        .where(Account.provider_id == provider_id)
        .where(User.status == 0)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: UUID) -> Optional[User]:
    """通过用户 ID 获取用户"""
    stmt = select(User).where(User.id == user_id).where(User.status == 0)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_user_with_roles_and_permissions(
    db: AsyncSession,
    user_id: UUID,
) -> Optional[User]:
    """获取用户及其角色和权限"""
    stmt = (
        select(User)
        .where(User.id == user_id)
        .where(User.status == 0)
        .options(
            selectinload(User.roles).selectinload(Role.permissions),
            selectinload(User.accounts),
        )
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_account_by_provider(
    db: AsyncSession,
    account_id: str,
    provider_id: str,
) -> Optional[Account]:
    """通过 provider 获取账户"""
    stmt = (
        select(Account)
        .where(Account.account_id == account_id)
        .where(Account.provider_id == provider_id)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def register_user(db: AsyncSession, username: str, email: str, password: str) -> User:
    """注册新用户"""
    # 检查用户名是否已存在
    stmt = select(User).where(User.username == username)
    result = await db.execute(stmt)
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名已存在",
        )

    # 检查邮箱是否已存在
    existing_account = await get_account_by_provider(db, email, "credentials")
    if existing_account:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="邮箱已被注册",
        )

    # 创建用户
    user = User(
        username=username,
        status=0,
    )
    db.add(user)
    await db.flush()

    # 创建账户
    account = Account(
        account_id=email,
        provider_id="credentials",
        user_id=user.id,
        password=get_password_hash(password),
    )
    db.add(account)
    await db.flush()

    return user


async def authenticate_user(db: AsyncSession, account_id: str, password: str) -> Optional[User]:
    """验证用户登录"""
    # 尝试通过邮箱查找
    user = await get_user_by_account(db, account_id, "credentials")
    # 通过邮箱找到用户，验证密码
    stmt = (
        select(Account)
        .where(Account.user_id == user.id)
        .where(Account.provider_id == "credentials")
        .where(Account.account_id == account_id)
    )
    result = await db.execute(stmt)
    account = result.scalar_one_or_none()
    if not account or not account.password:
        return None
    if not verify_password(password, account.password):
        return None

    return user


async def create_refresh_token_record(
    db: AsyncSession,
    user_id: UUID,
    token: str,
    expires_at: datetime,
    device_info: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> RefreshToken:
    """创建刷新令牌记录"""
    refresh_token = RefreshToken(
        id=uuid4(),
        user_id=user_id,
        token=token,
        expires_at=expires_at,
        is_revoked=False,
        device_info=device_info,
        user_agent=user_agent,
    )
    db.add(refresh_token)
    await db.flush()
    return refresh_token


async def get_refresh_token(
    db: AsyncSession,
    token: str,
) -> Optional[RefreshToken]:
    """获取刷新令牌记录"""
    stmt = (
        select(RefreshToken)
        .where(RefreshToken.token == token)
        .where(RefreshToken.is_revoked == False)
        .where(
            RefreshToken.expires_at
            > datetime.now(timezone.utc)
        )
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def revoke_refresh_token(
    db: AsyncSession,
    token: str,
) -> bool:
    """撤销刷新令牌"""
    refresh_token = await get_refresh_token(db, token)
    if not refresh_token:
        return False

    refresh_token.is_revoked = True
    refresh_token.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return True


async def get_user_roles(db: AsyncSession, user_id: UUID) -> List[str]:
    """获取用户的角色代码列表"""
    from app.models.role import UserRole
    stmt = (
        select(Role)
        .join(UserRole, Role.id == UserRole.role_id)
        .where(UserRole.user_id == user_id)
    )
    result = await db.execute(stmt)
    roles = result.scalars().all()
    return [role.code for role in roles]


async def get_user_permissions(db: AsyncSession, user_id: UUID) -> List[str]:
    """获取用户的所有权限代码列表"""
    from app.models.role import UserRole, RolePermission
    stmt = (
        select(Permission)
        .join(RolePermission, Permission.id == RolePermission.permission_id)
        .join(Role, RolePermission.role_id == Role.id)
        .join(UserRole, Role.id == UserRole.role_id)
        .where(UserRole.user_id == user_id)
    )
    result = await db.execute(stmt)
    permissions = result.scalars().all()
    # 去重
    return list(set([p.code for p in permissions]))


async def update_user_login_time(db: AsyncSession, user_id: UUID) -> None:
    """更新用户最后登录时间"""
    user = await get_user_by_id(db, user_id)
    if user:
        user.last_login_at = datetime.now(timezone.utc)
        await db.flush()
