"""基础检索服务（RH-20）。

公共知识库语义检索 + 个人知识库语义检索（按 user_id 隔离）+ 合并去重 + 返回来源。

权限要求（PLAN Day3 任务5）：
- 个人检索的 user_id 是「当前登录用户」由后端解析出来的内部 id，**不是**请求参数；
  调用方必须先 openid → users.id，再传进来，绝不接受客户端指定的 user_id。
- Qdrant 的 user_id 过滤只是第一道闸，真正的权限判定仍以 SQL 为准（RH-44 会加二次校验）。
"""
from __future__ import annotations

from pydantic import BaseModel

from qdrant_client import QdrantClient, models

from app.services.rag.embedding import EmbeddingService
from app.services.rag.schemas import PERSONAL_COLLECTION, PUBLIC_COLLECTION

__all__ = ["RetrievedChunk", "search_public", "search_personal", "search"]


class RetrievedChunk(BaseModel):
    """一条检索命中的 Chunk（含来源元数据），供上层拼上下文。"""

    document_id: str
    score: float
    title: str
    content: str
    document_type: str
    collection: str
    # 公共知识库字段
    recipe_id: int | None = None
    source: str | None = None
    category: str | None = None
    # 个人知识库字段
    user_id: int | None = None
    version: int | None = None
    verified: bool | None = None
    visibility: str | None = None
    chunk_index: int = 0
    total_chunks: int = 1


def _to_chunk(hit, collection: str) -> RetrievedChunk:
    p = hit.payload
    return RetrievedChunk(
        document_id=p.get("document_id", ""),
        score=hit.score,
        title=p.get("title", ""),
        content=p.get("content", ""),
        document_type=p.get("document_type", ""),
        collection=collection,
        recipe_id=p.get("recipe_id"),
        source=p.get("source"),
        category=p.get("category"),
        user_id=p.get("user_id"),
        version=p.get("version"),
        verified=p.get("verified"),
        visibility=p.get("visibility"),
        chunk_index=p.get("chunk_index", 0),
        total_chunks=p.get("total_chunks", 1),
    )


def search_public(
    client: QdrantClient,
    embedder: EmbeddingService,
    query: str,
    limit: int = 5,
) -> list[RetrievedChunk]:
    """公共知识库语义检索。"""
    vector = embedder.embed_query(query)
    res = client.query_points(collection_name=PUBLIC_COLLECTION, query=vector, limit=limit)
    return [_to_chunk(h, PUBLIC_COLLECTION) for h in res.points]


def search_personal(
    client: QdrantClient,
    embedder: EmbeddingService,
    query: str,
    user_id: int,
    limit: int = 5,
) -> list[RetrievedChunk]:
    """个人知识库语义检索，强制按 user_id 隔离。

    user_id 是调用方（后端）解析出的内部 users.id，这里用 Qdrant payload filter
    硬过滤，用户 A 无法检索到用户 B 的个人知识。
    """
    vector = embedder.embed_query(query)
    flt = models.Filter(
        must=[
            models.FieldCondition(
                key="user_id",
                match=models.MatchValue(value=user_id),
            )
        ]
    )
    res = client.query_points(
        collection_name=PERSONAL_COLLECTION,
        query=vector,
        query_filter=flt,
        limit=limit,
    )
    return [_to_chunk(h, PERSONAL_COLLECTION) for h in res.points]


def _merge(public: list[RetrievedChunk], personal: list[RetrievedChunk]) -> list[RetrievedChunk]:
    """合并两个库的结果：按 score 降序，document_id 去重（不同库前缀不同，天然唯一）。

    更细的「同一道菜在公共/个人各一份」去重留到上层（RH-21 上下文构建 / RH-24 推荐）
    按业务需要处理，这里只保证基础合并有序、不重复。
    """
    seen: set[str] = set()
    merged: list[RetrievedChunk] = []
    for chunk in sorted(public + personal, key=lambda c: c.score, reverse=True):
        if chunk.document_id in seen:
            continue
        seen.add(chunk.document_id)
        merged.append(chunk)
    return merged


def search(
    client: QdrantClient,
    embedder: EmbeddingService,
    query: str,
    user_id: int,
    public_limit: int = 5,
    personal_limit: int = 5,
) -> dict:
    """检索公共 + 个人两个库，返回分库结果与合并结果。"""
    public = search_public(client, embedder, query, public_limit)
    personal = search_personal(client, embedder, query, user_id, personal_limit)
    return {
        "public": public,
        "personal": personal,
        "merged": _merge(public, personal),
    }
