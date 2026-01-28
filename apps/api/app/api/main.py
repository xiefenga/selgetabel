from fastapi import APIRouter

from app.api.routes import chat, auth, file, thread

api_router = APIRouter()

api_router.include_router(chat.router)

api_router.include_router(auth.router)

api_router.include_router(file.router)

api_router.include_router(thread.router)

