"""Phase 0 启动校验：确保关键配置就位，缺失则报错退出"""

import logging
from typing import Dict

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# 必须存在的 LLM Stage（stage 名称 → 用途描述）
REQUIRED_STAGES: Dict[str, str] = {
    "chat": "纯文本对话（无文件时）",
    "generate": "JSON 操作生成",
    "analyze": "数据分析",
    "execute": "操作执行",
}


async def validate_llm_stage_configs(db: AsyncSession) -> None:
    """启动时校验 LLM stage 路由配置，缺失则报错退出"""
    from sqlalchemy import select

    from app.models.llm import LLMStageRoute

    result = await db.execute(
        select(LLMStageRoute).where(LLMStageRoute.is_active.is_(True))
    )
    routes = {r.stage: r for r in result.scalars().all()}

    missing = [f"  - {stage}: {desc}" for stage, desc in REQUIRED_STAGES.items() if stage not in routes]
    if missing:
        raise RuntimeError(
            f"LLM stage 路由未配置，请在管理后台配置以下 stage：\n" + "\n".join(missing)
        )

    logger.info(f"LLM stage 路由校验通过: {list(routes.keys())}")


async def validate_database_schema(db: AsyncSession) -> None:
    """
    启动时校验数据库模型字段是否存在。

    若 messages_history 字段缺失，告知用户先执行迁移。
    """
    def _check_schema(sync_session):
        from sqlalchemy import inspect
        inspector = inspect(sync_session.get_bind())
        columns = [c["name"] for c in inspector.get_columns("thread_turns")]
        if "messages_history" not in columns:
            raise RuntimeError(
                "缺少字段 ThreadTurn.messages_history，请先执行迁移：\n"
                "uv run alembic revision --autogenerate -m 'add messages_history to thread_turns'\n"
                "uv run alembic upgrade head"
            )
        logger.info("数据库模型校验通过")

    # AsyncSession.run_sync() 在事务外执行同步检查
    await db.run_sync(_check_schema)


async def run_startup_validations(db: AsyncSession) -> None:
    """
    执行所有启动校验（按顺序，任一失败则进程退出）。
    """
    await validate_database_schema(db)
    await validate_llm_stage_configs(db)
