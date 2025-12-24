from typing import AsyncGenerator
from sqlmodel import SQLModel
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

# 创建异步引擎
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,  # 在调试模式下打印SQL语句
    future=True
)

# 创建异步会话工厂
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)  # type: ignore[call-overload]


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """获取数据库会话"""
    async with AsyncSessionLocal() as session:
        yield session


async def init_db():
    """初始化数据库，创建所有表"""
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
