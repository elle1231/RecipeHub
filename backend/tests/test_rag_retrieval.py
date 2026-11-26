"""RH-20 基础检索服务的单元测试。

用 mock QdrantClient + 确定性 embedding，重点验证：
- 公共/个人检索走对 Collection；
- 个人检索强制带 user_id 过滤（隔离）；
- 合并结果按 score 降序、document_id 去重。
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

from qdrant_client import models

from app.services.rag.embedding import DeterministicEmbedding
from app.services.rag.retrieval import (
    RetrievedChunk,
    _merge,
    search,
    search_personal,
    search_public,
)
from app.services.rag.schemas import PERSONAL_COLLECTION, PUBLIC_COLLECTION


def _hit(doc_id, score, title, content, **extra):
    payload = {
        "document_id": doc_id,
        "title": title,
        "content": content,
        "document_type": "recipe",
        **extra,
    }
    return SimpleNamespace(score=score, payload=payload)


def _client_with_hits(mapping: dict) -> MagicMock:
    """mapping: {collection_name: [hit, ...]}"""
    client = MagicMock()

    def query_points(collection_name=None, query=None, query_filter=None, limit=None, **kw):
        hits = list(mapping.get(collection_name, []))
        if limit is not None:
            hits = hits[:limit]
        return SimpleNamespace(points=hits)

    client.query_points.side_effect = query_points
    return client


def test_search_public_uses_public_collection():
    client = _client_with_hits({
        PUBLIC_COLLECTION: [_hit("public_recipe_1#0", 0.6, "番茄炒蛋", "正文", recipe_id=1, source="s.md")],
    })
    embedder = DeterministicEmbedding(dimension=512)
    result = search_public(client, embedder, "番茄炒蛋怎么做", limit=3)

    assert len(result) == 1
    c = result[0]
    assert c.collection == PUBLIC_COLLECTION
    assert c.document_id == "public_recipe_1#0"
    assert c.recipe_id == 1 and c.source == "s.md"
    assert c.title == "番茄炒蛋" and c.content == "正文"
    # 走了正确的 Collection
    assert client.query_points.call_args.kwargs["collection_name"] == PUBLIC_COLLECTION


def test_search_personal_applies_user_id_filter():
    client = _client_with_hits({PERSONAL_COLLECTION: []})
    embedder = DeterministicEmbedding(dimension=512)
    search_personal(client, embedder, "我的菜怎么做", user_id=7)

    kwargs = client.query_points.call_args.kwargs
    assert kwargs["collection_name"] == PERSONAL_COLLECTION
    # 过滤条件必须是 user_id == 7（隔离的关键）
    expected = models.Filter(
        must=[models.FieldCondition(key="user_id", match=models.MatchValue(value=7))]
    )
    assert kwargs["query_filter"] == expected


def test_search_returns_merged_sorted_by_score():
    client = _client_with_hits({
        PUBLIC_COLLECTION: [
            _hit("public_recipe_1#0", 0.6, "菜A", "内容A", recipe_id=1),
            _hit("public_recipe_2#0", 0.4, "菜B", "内容B", recipe_id=2),
        ],
        PERSONAL_COLLECTION: [
            _hit("personal_recipe_7_100#0", 0.8, "我的菜", "内容C", recipe_id=100, user_id=7),
        ],
    })
    embedder = DeterministicEmbedding(dimension=512)
    result = search(client, embedder, "查询", user_id=7)

    assert len(result["public"]) == 2
    assert len(result["personal"]) == 1
    scores = [c.score for c in result["merged"]]
    assert scores == [0.8, 0.6, 0.4]
    assert result["merged"][0].document_id == "personal_recipe_7_100#0"


def test_merge_dedups_by_document_id():
    a = RetrievedChunk(document_id="x", score=0.9, title="t", content="c",
                       document_type="recipe", collection="c")
    b = a.model_copy()
    assert len(_merge([a], [b])) == 1
