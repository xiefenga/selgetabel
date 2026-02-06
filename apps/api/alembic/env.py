"""Alembic 环境配置 — 全程使用异步 (asyncpg)，与应用统一。"""

import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings
from app.core.base import Base
from app.models import *  # noqa: F401, F403

config = context.config

# 迁移沿用应用同样的 URL，保持 postgresql+asyncpg
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL_ASYNC)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # PostgreSQL 场景强烈建议
        transactional_ddl=False,  # 避免整包 SQL 被包进一个大事务
        compare_type=True,  # 类型变更可追踪
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    conf = config.get_section(config.config_ini_section, {})
    conf["sqlalchemy.url"] = settings.DATABASE_URL_ASYNC
    connectable = async_engine_from_config(
        conf,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
