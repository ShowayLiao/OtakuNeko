from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from app.db.database import init_db
from app.api import api_router
from app.core.config import settings
from app.core.logging import get_logger
from app.harness.scheduler.repository import SqlTaskRepository
from app.harness.scheduler import Scheduler
from app.harness.scheduler.execution import handle_task_def
from app.db.database import AsyncSessionLocal
from app.agents.agent_registry import AgentRegistry
from app.agents.router import AgentRouter
from app.agents.recommendation_agent import RecommendationAgent
from app.capabilities.recommendation import RecommendationCapability
from app.harness.runtime import AgentRuntime
from app.trace.store import InMemoryTraceStore


class _ScheduledAdapter:
    async def run(self, state):
        return {"status": "completed", "task_id": state.task.task_id}

# 缓存相关导入
from fastapi_cache import FastAPICache  # noqa: E402
from fastapi_cache.coder import PickleCoder  # noqa: E402
from fastapi_cache.backends.inmemory import InMemoryBackend  # noqa: E402
from redis.asyncio import Redis  # noqa: E402

# 初始化日志系统
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理，初始化数据库和缓存"""
    
    # 1. 数据库初始化
    # 如果是本地 SQLite，这一步会自动生成 .db 文件并建表
    # Never log credentials embedded in a database URL.
    logger.info("Initializing database connection")
    await init_db()
    logger.info("Database initialized successfully")
    app.state.proactive_repository = SqlTaskRepository(AsyncSessionLocal)
    app.state.proactive_scheduler = None
    if settings.ENABLE_PROACTIVE_SCHEDULER:
        # Wiring is explicit and isolated; deployments provide claim/handler
        # dependencies without changing the interactive API path.
        registry = AgentRegistry()
        registry.register("recommendation", RecommendationAgent(RecommendationCapability()))
        app.state.proactive_router = AgentRouter(registry)
        app.state.proactive_trace_store = InMemoryTraceStore()
        app.state.proactive_runtime = AgentRuntime(
            _ScheduledAdapter(), trace_store=app.state.proactive_trace_store
        )

        async def scheduled_handler(task_def, run):
            return await handle_task_def(
                task_def,
                run,
                app.state.proactive_runtime,
                app.state.proactive_router,
                repository=app.state.proactive_repository,
            )

        app.state.proactive_scheduler = Scheduler(
            lambda lease: app.state.proactive_repository.claim_due(
                datetime.now(timezone.utc), lease
            ),
            scheduled_handler,
        )
        await app.state.proactive_scheduler.start()
    
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
    
    # 3. 关闭资源
    if redis:
        try:
            await redis.close()
            logger.info("Redis connection closed")
        except Exception as e:
            logger.error(f"Failed to close Redis connection: {e}")

    if app.state.proactive_scheduler is not None:
        await app.state.proactive_scheduler.stop()
    
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
