"""API 依赖"""

from fastapi import HTTPException

from app.core.llm_client import LLMClient


def get_llm_client() -> LLMClient:
    """获取 LLM 客户端"""
    try:
        return LLMClient()
    except ValueError as e:
        raise HTTPException(status_code=500, detail=f"LLM 初始化失败: {e}")
