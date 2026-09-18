from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import computed_field

class Settings(BaseSettings):
    PROJECT_NAME: str = "OtakuNeko"
    API_V1_STR: str = "/api/v1"
    DEBUG: bool = True
    JWT_SECRET_KEY: str = ""
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:3001,http://localhost:3002,http://localhost:3003"
    OPENAI_API_KEY: Optional[str] = None

    # 1. 读取模式开关
    DEPLOY_MODE: str = "local"

    # Feature flags
    # Personalized chat needs the routing path so authenticated collection
    # data reaches RecommendationAgent instead of falling back to plain chat.
    ENABLE_MULTI_AGENT_ROUTING: bool = True
    ENABLE_PROACTIVE_SCHEDULER: bool = False

    # Checkpoint lifecycle. The local SQLite path remains the development
    # default; production deployments must provide a durable mounted path or
    # an adapter with equivalent persistence semantics.
    CHECKPOINT_DB_PATH: str = "data/checkpoints.db"
    HARNESS_CHECKPOINT_ADAPTER: str = "sqlite"
    HARNESS_CHECKPOINT_SINGLE_WORKER: bool = True
    HARNESS_WORKER_COUNT: int = 1
    CHECKPOINT_LEASE_SECONDS: int = 3600

    # Provider egress policy. Local development can opt out of DNS checks;
    # cloud deployments should enable resolution and configure the egress
    # allowlist at the network boundary as well.
    PROVIDER_RESOLVE_DNS: bool = False
    PROVIDER_ALLOWED_HOSTS: str = ""
    PROVIDER_ALLOWED_PORTS: str = "80,443"
    MODEL_CHECK_RATE_LIMIT: int = 5
    MODEL_CHECK_RATE_WINDOW_SECONDS: int = 60

    # 2. 读取 Local 模式配置
    SQLITE_FILE: str = "./local.db"

    # 3. 读取 Cloud 模式配置
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "otaku"
    POSTGRES_PASSWORD: str = "password"
    POSTGRES_DB: str = "otakuneko"
    REDIS_URL: Optional[str] = "redis://localhost:6379/0"

    # 4. QBittorrent 配置
    ENABLE_QB_PROXY: bool = True
    QB_HOST: str = "http://localhost:8080"
    QB_USERNAME: str = "admin"
    QB_PASSWORD: str = "123456"
    QB_ALLOWED_USER_IDS: str = ""

    # 4. 【核心逻辑】自动生成 DATABASE_URL
    @computed_field  # type: ignore[prop-decorator]  # Pydantic's decorator order is unsupported by mypy
    @property
    def DATABASE_URL(self) -> str:
        if self.DEPLOY_MODE == "local":
            return f"sqlite+aiosqlite:///{self.SQLITE_FILE}"
        else:
            return (
                f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
                f"@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
            )

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"

settings = Settings()
