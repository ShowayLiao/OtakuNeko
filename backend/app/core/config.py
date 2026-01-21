from typing import Optional
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

class Settings(BaseSettings):
    # 应用配置
    PROJECT_NAME: str = "OtakuNeko"
    API_V1_STR: str = "/api/v1"
    DEBUG: bool = True
    
    # 数据库配置
    DATABASE_URL: str = "postgresql+asyncpg://otaku:password@localhost:5432/otakuneko"
    
    # Redis配置
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # OpenAI配置
    OPENAI_API_KEY: Optional[str] = None
    
    # 日志配置
    LOG_LEVEL: str = "INFO"
    LOG_DIR: str = "logs"
    LOG_MAX_BYTES: int = 104857600  # 100MB
    LOG_BACKUP_COUNT: int = 30  # 保留30天的日志
    LOG_FORMAT: str = "%(asctime)s - %(levelname)s - %(module)s - %(request_id)s - %(message)s"
    LOG_DATE_FORMAT: str = "%Y-%m-%d %H:%M:%S"
    
    class Config:
        env_file = ".env"
        case_sensitive = True

# 创建配置实例
settings = Settings()
