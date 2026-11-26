"""向量索引构建：SQLite 读数据 → Chunking → Embedding → Qdrant Upsert（RH-19）。

编排逻辑放这里（可单测），脚本 scripts/build_vector_index.py 只做「读配置 → 调 build_index」的壳。
幂等：point id 由 document_id 经 uuid5 确定性生成，重复运行同 id 覆盖而非新增。
"""
from __future__ import annotations

import logging
import uuid

from qdrant_client import QdrantClient, models
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import CookingRecord, Recipe
from app.services.rag.chunking import (
    build_cooking_note_chunks,
    build_personal_recipe_chunks,
    build_public_chunks,
    format_ingredient,
    format_step,
)
from app.services.rag.embedding import EmbeddingService
from app.services.rag.schemas import PERSONAL_COLLECTION, PUBLIC_COLLECTION

logger = logging.getLogger(__name__)

__all__ = [
    "collect_public_chunks",
    "collect_personal_chunks",
    "embed_and_upsert",
    "build_index",
]


# ---------- 数据采集：SQLite → Chunk ----------

def collect_public_chunks(db: Session) -> list:
    """读公共菜谱（owner_id 为空），格式化 + 切块。"""
    recipes = db.scalars(select(Recipe).where(Recipe.owner_id.is_(None))).all()
    chunks = []
    for r in recipes:
        chunks.extend(
            build_public_chunks(
                recipe_id=r.id,
                title=r.title,
                description=r.description,
                ingredients=[format_ingredient(i) for i in r.ingredients],
                steps=[format_step(s) for s in r.steps],
                source=r.source,
                category=r.category,
            )
        )
    return chunks


def _format_record_content(record: CookingRecord) -> str:
    """把一条制作记录拼成可向量化的文本（只保留非空字段）。"""
    parts = []
    if record.rating is not None:
        parts.append(f"评分：{record.rating} 星")
    if record.problems:
        parts.append(f"问题：{record.problems}")
    if record.next_time_adjustment:
        parts.append(f"下次调整：{record.next_time_adjustment}")
    if record.actual_steps:
        parts.append(f"实际步骤：{record.actual_steps}")
    return "\n".join(parts) if parts else "制作记录"


def collect_personal_chunks(db: Session) -> list:
    """读个人菜谱（owner_id 非空）+ 制作记录，切块。

    user_id 一律用内部整数 users.id（recipes.owner_id / cooking_records.user_id），
    与 SQL 的归属口径一致。
    """
    chunks = []
    recipes = db.scalars(select(Recipe).where(Recipe.owner_id.is_not(None))).all()
    for r in recipes:
        chunks.extend(
            build_personal_recipe_chunks(
                user_id=r.owner_id,
                recipe_id=r.id,
                title=r.title,
                description=r.description,
                ingredients=[format_ingredient(i) for i in r.ingredients],
                steps=[format_step(s) for s in r.steps],
                version=r.current_version,
                verified=(r.status == "Verified"),
                visibility=r.visibility,
            )
        )

    records = db.scalars(select(CookingRecord)).all()
    for rec in records:
        title = rec.recipe.title if rec.recipe else "制作记录"
        chunks.extend(
            build_cooking_note_chunks(
                user_id=rec.user_id,
                record_id=rec.id,
                recipe_id=rec.recipe_id,
                title=title,
                content=_format_record_content(rec),
            )
        )
    return chunks


# ---------- 写入：Embedding → Qdrant ----------

def embed_and_upsert(
    client: QdrantClient,
    collection_name: str,
    chunks: list,
    embedder: EmbeddingService,
) -> int:
    """把一批 Chunk 编码成向量并 upsert 到指定 Collection，返回写入点数。"""
    if not chunks:
        return 0

    vectors = embedder.embed_texts([c.content for c in chunks])
    # 用「实际产出的向量维度」校验，比配置值更可靠：换模型但忘改 EMBEDDING_DIM 时，
    # 这里能立刻拦住，而不是等到 Qdrant 报「维度不符」。
    actual_dim = len(vectors[0]) if vectors else 0
    if actual_dim != settings.embedding_dim:
        raise ValueError(
            f"embedding 实际维度 {actual_dim} 与 Collection 维度 "
            f"{settings.embedding_dim} 不一致，换模型需先重建 Collection"
        )

    points = [
        models.PointStruct(
            id=str(uuid.uuid5(uuid.NAMESPACE_URL, chunk.document_id)),
            vector=vector,
            payload=chunk.model_dump(mode="json"),
        )
        for chunk, vector in zip(chunks, vectors)
    ]
    client.upsert(collection_name=collection_name, points=points)
    return len(points)


# ---------- 编排 ----------

def build_index(
    db: Session,
    client: QdrantClient,
    embedder: EmbeddingService,
    *,
    include_personal: bool = True,
) -> dict:
    """完整流程：采集 → 切块 → 写向量。返回统计信息。"""
    from app.services.rag.collections import ensure_collections

    ensure_collections(client)

    public_chunks = collect_public_chunks(db)
    public_points = embed_and_upsert(client, PUBLIC_COLLECTION, public_chunks, embedder)

    personal_chunks = collect_personal_chunks(db) if include_personal else []
    personal_points = embed_and_upsert(client, PERSONAL_COLLECTION, personal_chunks, embedder)

    return {
        "embedding": {"model": settings.embedding_model, "dimension": embedder.dimension},
        PUBLIC_COLLECTION: {"chunks": len(public_chunks), "points": public_points},
        PERSONAL_COLLECTION: {"chunks": len(personal_chunks), "points": personal_points},
    }
