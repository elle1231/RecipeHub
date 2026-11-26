"""RH-19 向量索引构建（采集 + 写入）的单元测试。

采集用临时 SQLite 真跑；写入用 mock QdrantClient + 真实 DeterministicEmbedding，
不依赖真实 Qdrant / 模型。
"""
import uuid
from unittest.mock import MagicMock

import pytest

from app.models import CookingRecord, Recipe, RecipeIngredient, RecipeStep
from app.services.rag.embedding import DeterministicEmbedding
from app.services.rag.index import (
    build_index,
    collect_personal_chunks,
    collect_public_chunks,
    embed_and_upsert,
)
from app.services.rag.schemas import (
    PERSONAL_COLLECTION,
    PUBLIC_COLLECTION,
    PublicRecipeChunk,
)
from app.services.user.service import get_or_create_user


def _make_recipe(db, *, owner_id=None, title="测试菜", source=None, category=None) -> Recipe:
    r = Recipe(
        owner_id=owner_id,
        title=title,
        source=source,
        category=category,
        status="Draft",
        visibility="private",
        orderable=False,
        current_version=1,
    )
    r.ingredients = [RecipeIngredient(sort_order=0, ingredient_name="番茄", quantity="2", unit="个")]
    r.steps = [RecipeStep(step_number=1, instruction="热锅翻炒")]
    db.add(r)
    db.commit()
    return r


# ---------- 采集 ----------

def test_collect_public_chunks(session_factory):
    db = session_factory()
    r = _make_recipe(db, owner_id=None, title="番茄炒蛋", source="s.md", category="家常菜")
    chunks = collect_public_chunks(db)
    db.close()

    assert len(chunks) == 1
    c = chunks[0]
    assert c.recipe_id == r.id
    assert c.title == "番茄炒蛋"
    assert c.source == "s.md"
    assert c.category == "家常菜"
    assert "番茄 2个" in c.content and "热锅翻炒" in c.content


def test_collect_personal_chunks_includes_recipes_and_records(session_factory):
    db = session_factory()
    user = get_or_create_user(db, "u1")
    r = _make_recipe(db, owner_id=user.id, title="我的番茄炒蛋")
    rec = CookingRecord(
        recipe_id=r.id, user_id=user.id, rating=5, problems="太咸", next_time_adjustment="下次少盐"
    )
    db.add(rec)
    db.commit()
    chunks = collect_personal_chunks(db)
    db.close()

    # 至少：个人菜谱 1 块 + 制作记录 1 块
    titles = {c.title for c in chunks}
    assert "我的番茄炒蛋" in titles
    note = [c for c in chunks if c.document_id.startswith("cooking_note_")]
    assert len(note) == 1
    assert "太咸" in note[0].content and "下次少盐" in note[0].content
    assert all(c.user_id == user.id for c in chunks)


# ---------- 写入 ----------

def test_embed_and_upsert_deterministic_id_and_payload():
    client = MagicMock()
    chunk = PublicRecipeChunk(
        document_id="public_recipe_1#0",
        recipe_id=1,
        title="t",
        content="正文",
        source=None,
        category=None,
    )
    embedder = DeterministicEmbedding(dimension=512)

    n = embed_and_upsert(client, PUBLIC_COLLECTION, [chunk], embedder)

    assert n == 1
    client.upsert.assert_called_once()
    kwargs = client.upsert.call_args.kwargs
    assert kwargs["collection_name"] == PUBLIC_COLLECTION

    point = kwargs["points"][0]
    assert point.id == str(uuid.uuid5(uuid.NAMESPACE_URL, "public_recipe_1#0"))
    assert len(point.vector) == 512
    assert point.payload["document_id"] == "public_recipe_1#0"
    assert point.payload["content"] == "正文"


def test_embed_and_upsert_rejects_dimension_mismatch():
    client = MagicMock()
    chunk = PublicRecipeChunk(document_id="x#0", recipe_id=1, title="t", content="c")
    embedder = DeterministicEmbedding(dimension=128)  # 与 settings.embedding_dim=512 不符

    with pytest.raises(ValueError):
        embed_and_upsert(client, PUBLIC_COLLECTION, [chunk], embedder)


def test_embed_and_upsert_empty_chunks_is_noop():
    client = MagicMock()
    embedder = DeterministicEmbedding(dimension=512)
    assert embed_and_upsert(client, PUBLIC_COLLECTION, [], embedder) == 0
    client.upsert.assert_not_called()


# ---------- 编排 ----------

def test_build_index_returns_stats(session_factory):
    db = session_factory()
    _make_recipe(db, owner_id=None, title="番茄炒蛋")
    client = MagicMock()
    embedder = DeterministicEmbedding(dimension=512)

    stats = build_index(db, client, embedder, include_personal=False)
    db.close()

    assert stats["embedding"]["dimension"] == 512
    assert stats[PUBLIC_COLLECTION]["points"] >= 1
    assert stats[PERSONAL_COLLECTION]["points"] == 0
    # 确实调用了 ensure_collections（collection_exists 被查询）
    client.collection_exists.assert_called()
