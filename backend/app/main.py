from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import aiosqlite
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from app.db.database import init_db
from app.api import api_router
from app.core.config import settings
from app.core.logging import get_logger

# 缓存相关导入
from fastapi_cache import FastAPICache
from fastapi_cache.coder import PickleCoder
from fastapi_cache.backends.inmemory import InMemoryBackend  # <--- 必须导入这个
from redis.asyncio import Redis
import logging

# 初始化日志系统
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理，初始化数据库和缓存"""
    
    # 1. 数据库初始化
    # 如果是本地 SQLite，这一步会自动生成 .db 文件并建表
    logger.info(f"Initializing database with URL: {settings.DATABASE_URL}")
    await init_db()
    logger.info("Database initialized successfully")

    conn = await aiosqlite.connect("checkpoints.db")
    app.state.checkpointer = AsyncSqliteSaver(conn)
    logger.info("Checkpoint saver initialized (SQLite)")
    
    # 2. 缓存初始化 (智能切换逻辑)
    redis = None
    
    # 判断是否为 SQLite (本地模式)
    is_local_mode = "sqlite" in settings.DATABASE_URL
    
    if is_local_mode:
        # === 分支 A: 本地模式 (无需 Redis) ===
        logger.info("🚀 Local mode (SQLite) detected. Using In-Memory Cache.")
        FastAPICache.init(
            InMemoryBackend(),
            expire=60,
            prefix="fastapi-cache-local",
            coder=PickleCoder
        )
        
    else:
        # === 分支 B: 生产模式 (Postgres + Redis) ===
        logger.info("🚀 Production mode detected. Attempting to connect to Redis...")
        try:
            # Pickle需要二进制数据，所以decode_responses设置为False
            redis = Redis.from_url(settings.REDIS_URL, decode_responses=False)
            # 测试连接
            await redis.ping()
            
            # 初始化FastAPICache (使用内存缓存作为备选方案)
            # 注意：由于版本兼容性问题，暂时使用内存缓存
            FastAPICache.init(
                InMemoryBackend(),
                expire=60,
                prefix="fastapi-cache-v2",
                coder=PickleCoder
            )
            logger.info("✅ Cache initialized successfully (using InMemoryBackend)")
            
        except Exception as e:
            # 生产环境如果 Redis 挂了，自动降级到内存，保证服务不崩
            logger.error(f"❌ Failed to initialize Redis: {e}")
            logger.warning("⚠️ Falling back to InMemoryBackend")
            FastAPICache.init(
                InMemoryBackend(),
                expire=60,
                prefix="fastapi-cache-fallback",
                coder=PickleCoder
            )
    
    yield
    
    if hasattr(app.state, "checkpointer"):
        await conn.close()
        logger.info("Checkpoint saver closed")

    # 3. 关闭资源
    if redis:
        try:
            await redis.close()
            logger.info("Redis connection closed")
        except Exception as e:
            logger.error(f"Failed to close Redis connection: {e}")
    
    await FastAPICache.clear()
    logger.info("Cache cleared")


# 创建 FastAPI 应用实例
app = FastAPI(
    title="OtakuNeko API",
    description="Bangumi full-category data management API",
    version="2.0.0",
    lifespan=lifespan  # 使用生命周期管理
)

# 配置 CORS 中间件
app.add_middleware(
    CORSMiddleware,
    # 允许多个本地开发端口
    allow_origins=[origin.strip() for origin in settings.CORS_ORIGINS.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],  # 允许所有HTTP方法
    allow_headers=["*"],  # 允许所有HTTP头
)

# 包含 API 路由
app.include_router(api_router)


@app.get("/")
async def root():
    return {"message": "OtakuNeko V2 Backend is running!"}


@app.get("/health")
async def health_check():
    return {"status": "ok"}