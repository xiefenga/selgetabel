from fastapi import APIRouter

from app.core.config import settings
from app.api.routes import chat, auth, file, thread

api_router = APIRouter()

api_router.include_router(chat.router)

api_router.include_router(auth.router)

api_router.include_router(file.router)

api_router.include_router(thread.router)

# 只在开发环境启用 fixture 路由
if settings.ENV == "development":
    from app.api.routes import fixture

    api_router.include_router(fixture.router)


