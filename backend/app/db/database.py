from typing import AsyncGenerator
from sqlmodel import SQLModel
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
    connect_args=connect_args  # <--- 将参数传入引擎
)

# --- 修改结束 ---

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
    # 注意：在生产环境通常推荐使用 alembic 进行迁移
    # 但保留此函数可以确保本地模式下自动建表，非常方便
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)