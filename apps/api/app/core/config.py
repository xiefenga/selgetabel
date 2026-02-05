"""配置"""

from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # 忽略 .env 中未声明的变量，避免 ValidationError
    )

    # 应用配置
    ENV: str = "production"  # development | production
    DEBUG: bool = False

    # 项目根目录（monorepo 根目录，用于访问 fixtures/ 等共享资源）
    # 默认假设当前工作目录是 apps/api，向上两级是项目根目录
    PROJECT_ROOT: Path = Path(__file__).parent.parent.parent.parent.parent

    # 数据库配置（应用与 Alembic 均使用 asyncpg，此处统一为 postgresql+asyncpg）
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/selgetabel"
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20

    # minio 配置
    MINIO_ENDPOINT: str = ""
    MINIO_ACCESS_KEY: str = ""
    MINIO_SECRET_KEY: str = ""
    MINIO_BUCKET: str = ""
    MINIO_PUBLIC_BASE: str = ""

    DEFAULT_AVATAR: str = "/storage/llm-excel/__SYS__/default_avatar.png"

    @property
    def DATABASE_URL_ASYNC(self) -> str:
        """始终返回 postgresql+asyncpg URL，供应用与 Alembic 使用。"""
        u = self.DATABASE_URL
        if u.startswith("postgresql://") and "+asyncpg" not in u and "+psycopg" not in u:
            return u.replace("postgresql://", "postgresql+asyncpg://", 1)
        return u

    # JWT 配置
    JWT_SECRET_KEY: str = "your-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # 密码加密
    BCRYPT_ROUNDS: int = 12

    # OpenAI 配置（与 llm_client / cli 使用的变量名一致）
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_API_BASE: Optional[str] = "https://api.openai.com/v1"
    OPENAI_BASE_URL: Optional[str] = None  # 兼容 .env 中的旧变量名
    OPENAI_MODEL: Optional[str] = None


settings = Settings()

