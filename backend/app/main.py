"""RecipeHub FastAPI 入口。

本地启动（在 backend 目录下）：
    uvicorn app.main:app --reload

健康检查：
    GET /health

启动时会自动按 models 定义建表（幂等）；也可手动执行
    python -m scripts.init_db
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import public_recipes_router, recipes_router, users_router
from app.core.config import settings
from app.db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时建表（幂等），保证干净环境也能直接跑起来。
    init_db()
    yield


app = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)

app.include_router(recipes_router)
app.include_router(public_recipes_router)
app.include_router(users_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "app": settings.app_name}
