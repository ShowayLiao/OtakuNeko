from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import computed_field # 新增这个导入

class Settings(BaseSettings):
    PROJECT_NAME: str = "OtakuNeko"
    API_V1_STR: str = "/api/v1"
    DEBUG: bool = True
    OPENAI_API_KEY: Optional[str] = None
    
    # 1. 读取模式开关
    DEPLOY_MODE: str = "local" # 默认为 local

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

    # 4. 【核心逻辑】自动生成 DATABASE_URL
    @computed_field
    @property
    def DATABASE_URL(self) -> str:
        if self.DEPLOY_MODE == "local":
            # 自动拼接 SQLite 链接
            return f"sqlite+aiosqlite:///{self.SQLITE_FILE}"
        else:
            # 自动拼接 Postgres 链接
            return (
                f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
                f"@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
            )

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore" # 忽略多余的配置项

settings = Settings()