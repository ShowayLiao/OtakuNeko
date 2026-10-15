from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

# --- 修改开始: 智能识别数据库类型并配置参数 ---

# 1. 定义连接参数
connect_args = {}

# 2. 如果检测到是 SQLite (本地模式)，必须添加 check_same_thread=False
# 否则在 FastAPI 的异步多线程环境下会报 "ProgrammingError"
if "sqlite" in settings.DATABASE_URL:
    connect_args = {"check_same_thread": False}

# 创建异步引擎
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,  # 设置为False，避免SQL语句输出泛滥
    future=True,
    connect_args=connect_args,  # <--- 将参数传入引擎
)

# --- 修改结束 ---

# 创建异步会话工厂
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)  # type: ignore[call-overload]


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """获取数据库会话"""
    async with AsyncSessionLocal() as session:
        yield session


async def init_db():
    """Initialize local databases through the same versioned path as the CLI."""
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    backend_root = Path(__file__).resolve().parents[2]
    config = Config(str(backend_root / "alembic.ini"))
    config.attributes["configure_logger"] = False

    def upgrade(connection):
        config.attributes["connection"] = connection
        command.upgrade(config, "head")

    async with engine.begin() as connection:
        await connection.run_sync(upgrade)
