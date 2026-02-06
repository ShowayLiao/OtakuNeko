from fastapi import APIRouter
from . import subjects, collections, dashboard, users, auth, bangumi

api_router = APIRouter(prefix="/v1")

api_router.include_router(auth.router, tags=["Auth"])
api_router.include_router(subjects.router, tags=["Subjects"])
api_router.include_router(collections.router, tags=["Collections"])
api_router.include_router(dashboard.router, tags=["Dashboard"])
api_router.include_router(users.router, tags=["Users"])
api_router.include_router(bangumi.router, tags=["Bangumi"])
