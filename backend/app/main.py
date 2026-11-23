"""RecipeHub FastAPI 入口。

本地启动（在 backend 目录下）：
    uvicorn app.main:app --reload

健康检查：
    GET /health
"""
from fastapi import FastAPI

from app.core.config import settings

app = FastAPI(title=settings.app_name, debug=settings.debug)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "app": settings.app_name}
