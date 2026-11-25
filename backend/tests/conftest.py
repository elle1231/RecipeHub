"""pytest 夹具：每个测试用独立的临时 SQLite，不污染开发库（recipehub.db）。

通过 `app.dependency_overrides` 把 `get_db` 换成指向临时库的会话工厂。
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.session import get_db
from app.main import app


@pytest.fixture()
def session_factory(tmp_path):
    """返回绑定临时 SQLite 的 sessionmaker（每个测试一个独立 db 文件）。"""
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}",
        connect_args={"check_same_thread": False},
    )
    # 确保所有模型都注册到 metadata 后再建表
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


@pytest.fixture()
def client(session_factory):
    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
