"""RH-17 双知识库 Collection 配置与幂等创建的单元测试。

用 MagicMock 模拟 QdrantClient，不依赖真实 Qdrant 服务，保证测试
在任何机器上都能跑（真实创建走 scripts/init_collections.py 验收）。
"""
from unittest.mock import MagicMock

from qdrant_client import models

from app.core.config import settings
from app.services.rag.collections import ensure_collections
from app.services.rag.schemas import PERSONAL_COLLECTION, PUBLIC_COLLECTION


def _client_with_existing(names: set[str] | None = None) -> MagicMock:
    """返回一个 collection_exists 会「命中 names」的假 client。"""
    names = names or set()
    client = MagicMock()
    client.collection_exists.side_effect = lambda name: name in names
    return client


def test_vector_dimension_matches_embedding_model():
    """维度必须由 embedding_model 决定，这里是 BGE-small-zh-v1.5 → 512。"""
    assert settings.embedding_dim == 512


def test_creates_both_collections_when_missing():
    client = _client_with_existing()
    created = ensure_collections(client)

    assert created == {PUBLIC_COLLECTION: True, PERSONAL_COLLECTION: True}

    # 两次 create_collection 都用了「维度=settings.embedding_dim + 余弦距离」。
    assert client.create_collection.call_count == 2
    for call in client.create_collection.call_args_list:
        assert call.kwargs["vectors_config"] == models.VectorParams(
            size=settings.embedding_dim, distance=models.Distance.COSINE
        )

    names = {call.kwargs["collection_name"] for call in client.create_collection.call_args_list}
    assert names == {PUBLIC_COLLECTION, PERSONAL_COLLECTION}


def test_skips_existing_collections():
    client = _client_with_existing({PUBLIC_COLLECTION, PERSONAL_COLLECTION})
    created = ensure_collections(client)

    assert created == {PUBLIC_COLLECTION: False, PERSONAL_COLLECTION: False}
    client.create_collection.assert_not_called()
    client.create_payload_index.assert_not_called()


def test_personal_indexes_include_user_id_for_isolation():
    """个人知识库必须给 user_id 建索引，这是 RH-20 按用户隔离检索的依赖。"""
    client = _client_with_existing()
    ensure_collections(client)

    indexed_fields = {
        call.kwargs["field_name"]: call.kwargs["field_schema"]
        for call in client.create_payload_index.call_args_list
    }
    assert indexed_fields["user_id"] == models.PayloadSchemaType.INTEGER
    assert indexed_fields["recipe_id"] == models.PayloadSchemaType.INTEGER
    assert indexed_fields["document_type"] == models.PayloadSchemaType.KEYWORD
    assert indexed_fields["visibility"] == models.PayloadSchemaType.KEYWORD
    assert indexed_fields["verified"] == models.PayloadSchemaType.BOOL


def test_public_indexes_cover_recipe_category_document_type():
    client = _client_with_existing()
    ensure_collections(client)

    public_indexed = {
        call.kwargs["field_name"]: call.kwargs["field_schema"]
        for call in client.create_payload_index.call_args_list
        if call.kwargs["collection_name"] == PUBLIC_COLLECTION
    }
    assert public_indexed == {
        "recipe_id": models.PayloadSchemaType.INTEGER,
        "category": models.PayloadSchemaType.KEYWORD,
        "document_type": models.PayloadSchemaType.KEYWORD,
    }
