from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.db.database import init_db
from app.api import api_router
from app.core.config import settings

# 缓存相关导入
from fastapi_cache import FastAPICache
from fastapi_cache.coder import PickleCoder
from fastapi_cache.backends.redis import RedisBackend
from redis.asyncio import Redis
import logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理，初始化数据库和缓存"""
    # 启动时初始化数据库
    await init_db()
    
    # 初始化Redis缓存
    redis = None
    try:
        # Pickle需要二进制数据，所以decode_responses设置为False
        redis = Redis.from_url(settings.REDIS_URL, decode_responses=False)
        # 测试连接
        await redis.ping()
        
        # 初始化FastAPICache，使用新的前缀避免旧缓存影响
        FastAPICache.init(
            RedisBackend(redis),
            expire=60,  # 全局默认过期时间为60秒
            prefix="fastapi-cache-v2",  # 使用新前缀，完全隔离旧缓存
            coder=PickleCoder  # 使用PickleCoder避免类型转换错误
        )
        logging.info("Redis cache initialized successfully")
    except Exception as e:
        logging.error(f"Failed to initialize Redis cache: {e}")
        # Redis连接失败时，使用InMemoryBackend作为降级方案
        from fastapi_cache.backends.inmemory import InMemoryBackend
        FastAPICache.init(
            InMemoryBackend(),
            expire=60,
            prefix="fastapi-cache",
            coder=PickleCoder  # 使用PickleCoder避免类型转换错误
        )
        logging.info("Fallback to InMemoryBackend for caching")
    
    yield
    
    # 关闭资源
    if redis:
        try:
            await redis.close()
            logging.info("Redis connection closed")
        except Exception as e:
            logging.error(f"Failed to close Redis connection: {e}")
    
    await FastAPICache.clear()
    logging.info("Cache cleared")


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
    allow_origins=["http://localhost:3000", "http://localhost:3001", "http://localhost:3002", "http://localhost:3003"],  # 允许多个本地开发端口
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
