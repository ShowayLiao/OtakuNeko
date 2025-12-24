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
    
    class Config:
        env_file = ".env"
        case_sensitive = True

# 创建配置实例
settings = Settings()
