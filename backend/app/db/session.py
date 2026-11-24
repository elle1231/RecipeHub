"""数据库引擎、会话与建表。

- engine：全局唯一的 SQLAlchemy 引擎，连接 SQLite。
- SessionLocal：每个请求一个会话的工厂。
- get_db：FastAPI 依赖，用完自动关闭会话。
- init_db：按 models 里定义的表结构建表（幂等，表已存在则跳过）。
"""
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.db.base import Base

# SQLite 在多线程（FastAPI 默认把同步依赖丢进线程池）下需要关闭
# 单线程检查，否则会报 "SQLite objects created in a thread can only
# be used in that same thread"。
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine = create_engine(settings.database_url, connect_args=connect_args)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI 依赖：提供一个请求级数据库会话。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """按当前 models 定义建表（幂等）。"""
    # 延迟 import，确保所有模型都注册到 Base.metadata 后再 create_all。
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
