"""LangChain ChatModel 全局访问接口"""

import logging
from typing import Dict

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.llm_adapters.langchain_adapter import RegistryChatModel
from app.engine.llm_types import LLMStageConfig
from app.services.llm_config import load_stage_configs

logger = logging.getLogger(__name__)

_chat_model_cache: Dict[str, RegistryChatModel] = {}


async def get_langchain_chat_model(
    stage: str,
    db: AsyncSession,
) -> RegistryChatModel:
    """
    获取指定 stage 的 LangChain ChatModel（module-level 缓存）。

    Args:
        stage: stage 名称（如 "chat", "generate"）
        db: AsyncSession（用于加载配置）

    Returns:
        RegistryChatModel 实例
    """
    if stage in _chat_model_cache:
        return _chat_model_cache[stage]

    # 从 DB 加载所有 stage 配置（复用 llm_config.py 的逻辑）
    all_configs = await load_stage_configs(db)

    if stage not in all_configs:
        raise ValueError(
            f"Stage '{stage}' 未配置，请在管理后台配置。\n"
            f"已配置的 stage: {list(all_configs.keys())}"
        )

    stage_config = all_configs[stage]
    chat_model = RegistryChatModel(stage_config=stage_config)
    _chat_model_cache[stage] = chat_model
    logger.info(f"RegistryChatModel 缓存: stage={stage}, model={stage_config.model.model_id}")
    return chat_model


def clear_chat_model_cache() -> None:
    """清除缓存（用于配置变更时）"""
    _chat_model_cache.clear()
