"""认证相关路由"""

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.jwt import verify_token, create_access_token, create_refresh_token
from app.models.user import User, Account
from app.schemas.auth import (
    RegisterParams,
    LoginParams,
    UpdateUserParams,
    ChangePasswordRequest,
    BindAccountRequest,
    AccountInfo,
    UserInfo,
)
from app.schemas.response import ApiResponse
from app.services.auth import (
    register_user,
    authenticate_user,
    get_user_with_roles_and_permissions,
    create_refresh_token_record,
    get_refresh_token,
    revoke_refresh_token,
    get_user_roles,
    update_user_login_time,
    get_password_hash,
    verify_password,
    get_account_by_provider,
    get_user_by_id,
)
from app.core.config import settings

router = APIRouter(prefix="/auth", tags=["认证"])

@router.post("/register", response_model=ApiResponse[None], summary="用户注册")
async def register(register_params: RegisterParams, db: AsyncSession = Depends(get_db)):
    """用户注册"""
    try:
        await register_user(
            db=db,
            username=register_params.username,
            email=str(register_params.email),  # EmailStr 转换为 str
            password=register_params.password,
        )

        return ApiResponse(code=0, data=None, msg="注册成功")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"注册失败: {str(e)}",
        )


@router.post("/login", response_model=ApiResponse[UserInfo], summary="用户登录")
async def login(params: LoginParams, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    """用户登录，token 通过 cookie 返回"""
    user = await authenticate_user(db, params.account, params.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

    # 获取用户角色
    roles = await get_user_roles(db, user.id)

    # 创建访问令牌
    access_token = create_access_token(
        user_id=user.id,
        username=user.username,
        roles=roles,
    )

    # 创建刷新令牌
    expires_at = datetime.now(timezone.utc) + timedelta(
        days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS
    )
    refresh_token_id = uuid4()
    refresh_token_str = create_refresh_token(
        user_id=user.id,
        token_id=refresh_token_id,
    )

    # 获取 User-Agent
    user_agent = request.headers.get("user-agent")

    # 保存刷新令牌
    refresh_token_record = await create_refresh_token_record(
        db=db,
        user_id=user.id,
        token=refresh_token_str,
        expires_at=expires_at,
        user_agent=user_agent,
    )

    # 更新登录时间
    await update_user_login_time(db, user.id)

    # 获取用户完整信息（包括角色和权限）
    user_with_info = await get_user_with_roles_and_permissions(db, user.id)
    if not user_with_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在",
        )

    # 获取角色和权限
    roles_list = [role.code for role in user_with_info.roles]
    permissions_list = []
    for role in user_with_info.roles:
        for permission in role.permissions:
            permissions_list.append(permission.code)
    permissions_list = list(set(permissions_list))  # 去重

    # 获取 credentials 账户邮箱（用于 UserInfo.accounts.email）
    credentials_email = None
    for account in user_with_info.accounts:
        if account.provider_id == "credentials":
            credentials_email = account.account_id
            break

    # 设置 cookie
    # Access Token 过期时间（分钟转秒）
    access_token_max_age = settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60
    # Refresh Token 过期时间（天转秒）
    refresh_token_max_age = settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60

    response.set_cookie(
        key="access_token",
        value=access_token,
        max_age=access_token_max_age,
        httponly=True,
        secure=False,  # 生产环境应设置为 True（HTTPS）
        samesite="lax",
    )

    response.set_cookie(
        key="refresh_token",
        value=refresh_token_str,
        max_age=refresh_token_max_age,
        httponly=True,
        secure=False,  # 生产环境应设置为 True（HTTPS）
        samesite="lax",
    )

    return ApiResponse(
        code=0,
        data=UserInfo(
            id=user_with_info.id,
            username=user_with_info.username,
            avatar=user_with_info.avatar,
            status=user_with_info.status,
            accounts=AccountInfo(
                email=credentials_email or "",
            ),
            roles=roles_list,
            permissions=permissions_list,
            created_at=user_with_info.created_at.isoformat(),
            last_login_at=user_with_info.last_login_at.isoformat() if user_with_info.last_login_at else None,
        ),
        msg="登录成功",
    )


@router.post("/refresh", response_model=ApiResponse[None], summary="刷新访问令牌")
async def refresh(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    """刷新访问令牌，从 cookie 读取 refresh_token，新的 access_token 通过 cookie 返回"""
    # 从 cookie 读取刷新令牌
    refresh_token_str = request.cookies.get("refresh_token")
    if not refresh_token_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供刷新令牌",
        )

    # 验证刷新令牌
    payload = verify_token(refresh_token_str, token_type="refresh")
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的刷新令牌",
        )

    # 检查数据库中的刷新令牌
    refresh_token_record = await get_refresh_token(db, refresh_token_str)
    if not refresh_token_record:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="刷新令牌已失效或已撤销",
        )

    user_id = UUID(payload["sub"])
    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在或已被禁用",
        )

    # 获取用户角色
    roles = await get_user_roles(db, user.id)

    # 创建新的访问令牌
    access_token = create_access_token(
        user_id=user.id,
        username=user.username,
        roles=roles,
    )

    # 通过 cookie 返回新的 access_token
    access_token_max_age = settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60
    response.set_cookie(
        key="access_token",
        value=access_token,
        max_age=access_token_max_age,
        httponly=True,
        secure=False,  # 生产环境应设置为 True（HTTPS）
        samesite="lax",
    )

    return ApiResponse(
        code=0,
        data=None,
        msg="刷新成功",
    )


@router.post("/logout", response_model=ApiResponse[None], summary="用户登出")
async def logout(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    """用户登出，从 cookie 读取 refresh_token，并清除所有认证 cookie"""
    # 从 cookie 读取刷新令牌
    refresh_token_str = request.cookies.get("refresh_token")
    if refresh_token_str:
        # 撤销刷新令牌
        await revoke_refresh_token(db, refresh_token_str)

    # 清除所有认证相关的 cookie
    response.delete_cookie(key="access_token")
    response.delete_cookie(key="refresh_token")

    return ApiResponse(
        code=0,
        data=None,
        msg="登出成功",
    )


@router.get("/me", response_model=ApiResponse[UserInfo], summary="获取当前用户信息")
async def get_current_user_info(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """获取当前用户信息"""
    user = await get_user_with_roles_and_permissions(db, current_user.id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在",
        )

    # 获取角色和权限
    roles = [role.code for role in user.roles]
    permissions = []
    for role in user.roles:
        for permission in role.permissions:
            permissions.append(permission.code)
    permissions = list(set(permissions))  # 去重

    # 获取 credentials 账户邮箱（用于 UserInfo.accounts.email）
    credentials_email = None
    for account in user.accounts:
        if account.provider_id == "credentials":
            credentials_email = account.account_id
            break

    return ApiResponse(
        code=0,
        data=UserInfo(
            id=user.id,
            username=user.username,
            avatar=user.avatar,
            status=user.status,
            accounts=AccountInfo(
                email=credentials_email or "",
            ),
            roles=roles,
            permissions=permissions,
            created_at=user.created_at.isoformat(),
            last_login_at=user.last_login_at.isoformat() if user.last_login_at else None,
        ),
        msg="获取成功",
    )


@router.put("/me", response_model=ApiResponse[UserInfo], summary="更新用户信息")
async def update_user_info(params: UpdateUserParams, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """更新用户信息"""
    user = await get_user_by_id(db, current_user.id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在",
        )

    if params.username is not None:
        # 检查用户名是否已被使用
        stmt = select(User).where(User.username == params.username).where(User.id != user.id)
        result = await db.execute(stmt)
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="用户名已被使用",
            )
        user.username = params.username

    if params.avatar is not None:
        user.avatar = params.avatar

    user.updated_at = datetime.now(timezone.utc)

    # 获取更新后的用户信息
    user = await get_user_with_roles_and_permissions(db, user.id)
    roles = [role.code for role in user.roles]
    permissions = []
    for role in user.roles:
        for permission in role.permissions:
            permissions.append(permission.code)
    permissions = list(set(permissions))

    # 获取 credentials 账户邮箱（用于 UserInfo.accounts.email）
    credentials_email = None
    for account in user.accounts:
        if account.provider_id == "credentials":
            credentials_email = account.account_id
            break

    return ApiResponse(
        code=0,
        data=UserInfo(
            id=user.id,
            username=user.username,
            avatar=user.avatar,
            status=user.status,
            accounts=AccountInfo(
                email=credentials_email or "",
            ),
            roles=roles,
            permissions=permissions,
            created_at=user.created_at.isoformat(),
            last_login_at=user.last_login_at.isoformat() if user.last_login_at else None,
        ),
        msg="更新成功",
    )


@router.put("/password", response_model=ApiResponse[None], summary="修改密码")
async def change_password(request: ChangePasswordRequest, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """修改密码"""
    # 获取用户的 credentials 账户
    stmt = (
        select(Account)
        .where(Account.user_id == current_user.id)
        .where(Account.provider_id == "credentials")
    )
    result = await db.execute(stmt)
    account = result.scalar_one_or_none()

    if not account or not account.password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="未找到密码账户",
        )

    # 验证旧密码
    if not verify_password(request.old_password, account.password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="旧密码错误",
        )

    # 更新密码
    account.password = get_password_hash(request.new_password)
    account.updated_at = datetime.now(timezone.utc)

    return ApiResponse(
        code=0,
        data=None,
        msg="密码修改成功",
    )


@router.post("/bind-account", response_model=ApiResponse[None], summary="绑定新账户")
async def bind_account(
    request: BindAccountRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """绑定新的登录账户"""
    # 检查账户是否已被使用
    existing_account = await get_account_by_provider(db, request.account_id, request.provider_id)
    if existing_account:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该账户已被绑定",
        )

    # 如果是 credentials，需要密码
    if request.provider_id == "credentials":
        if not request.password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="credentials 登录方式需要提供密码",
            )

    # 创建新账户
    account = Account(
        id=uuid4(),
        account_id=request.account_id,
        provider_id=request.provider_id,
        user_id=current_user.id,
        password=get_password_hash(request.password) if request.password else None,
    )
    db.add(account)

    return ApiResponse(
        code=0,
        data=None,
        msg="账户绑定成功",
    )
