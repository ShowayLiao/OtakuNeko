from fastapi import APIRouter
from . import subjects, collections, dashboard

# 创建 v1 版本的路由包含器
api_router = APIRouter(prefix="/v1")

# 包含各个模块的路由
api_router.include_router(subjects.router, tags=["Subjects"])
api_router.include_router(collections.router, tags=["Collections"])
api_router.include_router(dashboard.router, tags=["Dashboard"])
