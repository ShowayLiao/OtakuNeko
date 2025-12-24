from fastapi import APIRouter
from .v1 import api_router as v1_router

# 创建主 API 路由包含器
api_router = APIRouter()

# 包含 v1 版本的路由
api_router.include_router(v1_router, prefix="/api")
