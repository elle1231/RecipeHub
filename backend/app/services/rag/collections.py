"""Qdrant 双知识库 Collection 的创建与配置（RH-17）。

定死两件事：
1. 向量参数：维度 = settings.embedding_dim（BGE-small-zh-v1.5 → 512），
   距离 = 余弦相似度（Cosine）。换模型后维度不兼容，要删库重建。
2. Payload 索引：把检索时要过滤的字段建索引，让 Qdrant 的
   payload filter（如按 user_id 隔离个人知识）走索引而不是全表扫。

`ensure_collections()` 幂等：Collection 已存在就跳过，可反复调用。
"""
from __future__ import annotations

import logging

from qdrant_client import QdrantClient
from qdrant_client import models

from app.core.config import settings
from app.services.rag.schemas import (
    PERSONAL_COLLECTION,
    PUBLIC_COLLECTION,
)

logger = logging.getLogger(__name__)

__all__ = ["ensure_collections", "collection_exists", "PUBLIC_COLLECTION", "PERSONAL_COLLECTION"]

# 距离度量：BGE 系列通常配合归一化向量 + 余弦相似度使用。
_DISTANCE = models.Distance.COSINE


def _vector_params() -> models.VectorParams:
    """两个 Collection 共用的向量参数。维度来自 settings.embedding_dim。"""
    return models.VectorParams(size=settings.embedding_dim, distance=_DISTANCE)


def collection_exists(client: QdrantClient, name: str) -> bool:
    """判断 Collection 是否已存在。"""
    return client.collection_exists(name)


def ensure_collections(client: QdrantClient) -> dict[str, bool]:
    """确保两个 Collection 存在，返回每个 Collection 本次是否被创建。

    幂等：已存在则不改动（不会因为重复启动而丢数据或报错）。
    """
    created: dict[str, bool] = {}

    if not client.collection_exists(PUBLIC_COLLECTION):
        client.create_collection(
            collection_name=PUBLIC_COLLECTION,
            vectors_config=_vector_params(),
        )
        created[PUBLIC_COLLECTION] = True
    else:
        created[PUBLIC_COLLECTION] = False

    if not client.collection_exists(PERSONAL_COLLECTION):
        client.create_collection(
            collection_name=PERSONAL_COLLECTION,
            vectors_config=_vector_params(),
        )
        created[PERSONAL_COLLECTION] = True
    else:
        created[PERSONAL_COLLECTION] = False

    # Payload 索引：只在「刚创建」的 Collection 上建，避免每次启动重复建索引。
    # （建索引幂等，但减少不必要的请求。）
    if created[PUBLIC_COLLECTION]:
        _create_public_indexes(client)
    if created[PERSONAL_COLLECTION]:
        _create_personal_indexes(client)

    return created


def _create_public_indexes(client: QdrantClient) -> None:
    """公共知识库按 recipe_id / category / document_type 建过滤索引。"""
    for field, schema_type in [
        ("recipe_id", models.PayloadSchemaType.INTEGER),
        ("category", models.PayloadSchemaType.KEYWORD),
        ("document_type", models.PayloadSchemaType.KEYWORD),
    ]:
        client.create_payload_index(
            collection_name=PUBLIC_COLLECTION,
            field_name=field,
            field_schema=schema_type,
        )


def _create_personal_indexes(client: QdrantClient) -> None:
    """个人知识库按 user_id / recipe_id / document_type / visibility / verified 建索引。

    user_id 索引是关键：RH-20 检索个人知识时必须按它隔离，防止串数据。
    """
    for field, schema_type in [
        ("user_id", models.PayloadSchemaType.INTEGER),
        ("recipe_id", models.PayloadSchemaType.INTEGER),
        ("document_type", models.PayloadSchemaType.KEYWORD),
        ("visibility", models.PayloadSchemaType.KEYWORD),
        ("verified", models.PayloadSchemaType.BOOL),
    ]:
        client.create_payload_index(
            collection_name=PERSONAL_COLLECTION,
            field_name=field,
            field_schema=schema_type,
        )
