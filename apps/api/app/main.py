"""LLM Excel API 服务入口"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from dotenv import load_dotenv

from app.api.main import api_router
from app.schemas.response import ApiResponse

load_dotenv()


OPENAPI_DESCRIPTION = """

🚀 **使用大语言模型智能处理 Excel 数据**

## 功能特性

- 📤 **文件上传**: 支持多文件上传，自动解析 Excel 表结构
- 🤖 **智能处理**: 使用自然语言描述数据处理需求，LLM 自动生成处理逻辑
- 📊 **多种操作**: 支持筛选、排序、分组聚合、新增列、跨表关联等
- 📥 **结果导出**: 处理结果可导出为 Excel 文件

"""

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期"""
    yield


app = FastAPI(
    title="LLM Excel API",
    description=OPENAPI_DESCRIPTION,
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """统一处理 HTTPException，返回统一格式的响应"""
    return JSONResponse(
        status_code=exc.status_code,
        content=ApiResponse(
            code=exc.status_code,
            data=None,
            msg=exc.detail
        ).model_dump()
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """统一处理其他异常，返回统一格式的响应"""
    return JSONResponse(
        status_code=500,
        content=ApiResponse(
            code=500,
            data=None,
            msg=f"服务器内部错误: {str(exc)}"
        ).model_dump()
    )


@app.get("/", include_in_schema=False)
async def root():
    """根路径重定向到 API 文档"""
    return RedirectResponse(url="/docs")


app.include_router(api_router)

