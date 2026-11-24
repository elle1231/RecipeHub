"""Qdrant 向量数据库连接（RH-04）。

后续使用：
- RH-17 在这里创建 Collection
- RH-19 写入向量
- RH-20 检索

本模块只负责「拿到客户端连接」，业务逻辑放 services/rag。
"""
from qdrant_client import QdrantClient

from app.core.config import settings


def get_qdrant_client() -> QdrantClient:
    """返回一个连接到本地 Qdrant 的客户端。

    构造 QdrantClient 本身不会立刻连接，真正建立连接发生在
    调用它的方法（如 get_collections()）时。
    """
    return QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)
