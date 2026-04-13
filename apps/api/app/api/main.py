from fastapi import APIRouter

from app.core.config import settings
from app.api.routes import auth, btrack, chat, file, llm, role, thread, user

api_router = APIRouter()

# 统一入口：意图识别 + 聊天路由（必须放在最前面）
api_router.include_router(chat.router, tags=["聊天"])

api_router.include_router(auth.router, tags=["认证"])

api_router.include_router(file.router, tags=["文件"])

api_router.include_router(thread.router, tags=["线程"])

api_router.include_router(btrack.router, tags=["错误跟踪"])

api_router.include_router(role.router, tags=["角色"])

api_router.include_router(user.router, tags=["用户"])

api_router.include_router(llm.router, tags=["LLM配置"])

