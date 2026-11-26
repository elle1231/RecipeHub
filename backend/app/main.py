"""RecipeHub FastAPI 入口。

本地启动（在 backend 目录下）：
    uvicorn app.main:app --reload

健康检查：
    GET /health

启动时会自动按 models 定义建表（幂等）；也可手动执行
    python -m scripts.init_db
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import public_recipes_router, recipes_router, users_router
from app.core.config import settings
from app.db import init_db

logger = logging.getLogger(__name__)


def _ensure_qdrant_collections() -> None:
    """幂等创建 Qdrant 双 Collection（RH-17）。

    Qdrant 未启动 / 网络异常时只告警不阻塞启动——保证「干净环境 + SQLite」
    也能先把 API 跑起来，稍后再用 scripts/init_collections.py 补建。
    """
    try:
        from app.db.qdrant import get_qdrant_client
        from app.services.rag.collections import ensure_collections

        created = ensure_collections(get_qdrant_client())
        logger.info("Qdrant Collection 就绪：%s", created)
    except Exception as exc:  # noqa: BLE001 —— 基础设施降级，宁可启动也不硬崩
        logger.warning("Qdrant Collection 初始化失败，可稍后运行 scripts/init_collections.py：%s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时建表（幂等）+ 建向量 Collection（幂等），保证干净环境也能直接跑起来。
    init_db()
    _ensure_qdrant_collections()
    yield


app = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)

app.include_router(recipes_router)
app.include_router(public_recipes_router)
app.include_router(users_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "app": settings.app_name}
