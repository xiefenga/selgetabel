"""认证相关的请求和响应模型"""

from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, Field, EmailStr


class RegisterParams(BaseModel):
    """用户注册请求"""

    username: str = Field(..., min_length=3, max_length=50, description="用户名")
    email: EmailStr = Field(..., description="邮箱地址")
    password: str = Field(..., min_length=6, max_length=100, description="密码")


class LoginParams(BaseModel):
    """用户登录请求"""

    account: str = Field(..., description="登录账户（邮箱或用户名）")
    password: str = Field(..., description="密码")


class RefreshTokenParams(BaseModel):
    """刷新令牌请求"""

    refresh_token: str = Field(..., description="刷新令牌")


class LogoutRequest(BaseModel):
    """登出请求"""

    refresh_token: str = Field(..., description="刷新令牌")


class UpdateUserParams(BaseModel):
    """更新用户信息请求"""

    username: Optional[str] = Field(None, min_length=3, max_length=50, description="用户名")
    avatar: Optional[str] = Field(None, max_length=512, description="头像 URL")


class ChangePasswordRequest(BaseModel):
    """修改密码请求"""

    old_password: str = Field(..., description="旧密码")
    new_password: str = Field(..., min_length=6, max_length=100, description="新密码")


class BindAccountRequest(BaseModel):
    """绑定新账户请求"""

    account_id: str = Field(..., description="账户标识（邮箱、手机号等）")
    provider_id: str = Field(..., description="登录方式（credentials, github, google 等）")
    password: Optional[str] = Field(None, min_length=6, max_length=100, description="密码（credentials 时必填）")


class TokenResponse(BaseModel):
    """令牌响应"""

    access_token: str = Field(..., description="访问令牌")
    refresh_token: str = Field(..., description="刷新令牌")
    token_type: str = Field(default="bearer", description="令牌类型")


class AccountInfo(BaseModel):
    """账户信息"""

    # account_type: str = Field(..., description="账号类型：local / oauth / sso")
    # provider: Optional[str] = Field(
    #     None, description="第三方提供方标识，例如 github、google、wechat 等"
    # )
    email: str = Field(..., description="登录邮箱")
    # phone: Optional[str] = Field(None, description="登录手机号")
    # login_count: int = Field(default=0, description="累计登录次数")
    # last_login_ip: Optional[str] = Field(None, description="最后登录 IP")
    # last_login_device: Optional[str] = Field(None, description="最后登录设备信息")
    # last_login_location: Optional[str] = Field(None, description="最后登录地，例如城市/国家")


class UserInfo(BaseModel):
    """用户信息响应"""

    id: UUID = Field(..., description="用户 ID")
    username: str = Field(..., description="用户名")
    avatar: Optional[str] = Field(None, description="头像 URL")
    status: int = Field(..., description="状态：0 正常，1 禁用")
    accounts: AccountInfo = Field(..., description="该用户所有登录账户")
    roles: List[str] = Field(default_factory=list, description="角色代码列表")
    permissions: List[str] = Field(default_factory=list, description="权限代码列表")
    created_at: str = Field(..., description="创建时间")
    last_login_at: Optional[str] = Field(None, description="最后登录时间")

