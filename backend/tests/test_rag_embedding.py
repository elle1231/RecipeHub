"""RH-17 Embedding 服务抽象与确定性桩的单元测试。

真实模型（本地 BGE / OpenAI 兼容 API）在 RH-19 接入，这里只锁住
接口契约：维度、批量顺序、确定性。
"""
from app.core.config import settings
from app.services.rag.embedding import DeterministicEmbedding, get_embedding_service


def test_dimension_matches_settings():
    svc = DeterministicEmbedding()
    assert svc.dimension == settings.embedding_dim


def test_returns_one_vector_per_text_in_order():
    svc = DeterministicEmbedding(dimension=512)
    vectors = svc.embed_texts(["番茄炒蛋", "红烧肉", "清蒸鱼"])
    assert len(vectors) == 3
    assert all(len(v) == 512 for v in vectors)


def test_same_text_gives_same_vector():
    svc = DeterministicEmbedding(dimension=512)
    a = svc.embed_texts(["番茄炒蛋"])[0]
    b = svc.embed_texts(["番茄炒蛋"])[0]
    assert a == b


def test_different_texts_give_different_vectors():
    svc = DeterministicEmbedding(dimension=512)
    a, b = svc.embed_texts(["番茄炒蛋", "清蒸鱼"])
    assert a != b


def test_factory_returns_embedding_service():
    """工厂当前返回确定性桩，RH-19 会按 settings 切换真实模型。"""
    svc = get_embedding_service()
    assert svc.dimension == settings.embedding_dim
