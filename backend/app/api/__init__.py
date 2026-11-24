"""API 路由聚合。main.py 直接从这里 import 各 router。"""
from app.api.public_recipes import router as public_recipes_router
from app.api.recipes import router as recipes_router
from app.api.users import router as users_router

__all__ = ["recipes_router", "public_recipes_router", "users_router"]
