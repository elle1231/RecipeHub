"""Embedding 服务抽象（RH-17）。

职责：把一段文本变成一组浮点向量。向量维度必须和 Qdrant Collection
的配置一致（RH-17 建 Collection 时按 settings.embedding_dim 定死）。

当前状态：真实模型（本地 BGE / OpenAI 兼容 API）到 RH-19 写向量时才
真正接入，因为那一步才需要「成批地把 169 道菜谱正文编码成向量」。
RH-17 只把接口和维度定下来，并提供 DeterministicEmbedding 作为
「测试 / 无模型联调」的可替换方案——它不产生语义向量，只保证
「同一段文本永远得到同一个向量」，用来打通 Collection 与检索链路。
"""
from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod

from app.core.config import settings

__all__ = ["EmbeddingService", "DeterministicEmbedding", "get_embedding_service"]


class EmbeddingService(ABC):
    """把文本编码为向量的服务。所有后端（本地 BGE / API / 测试桩）都实现它。"""

    dimension: int

    @abstractmethod
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """把一批文本编码为向量，返回顺序与输入一致。"""
        raise NotImplementedError


class DeterministicEmbedding(EmbeddingService):
    """确定性哈希向量：仅用于测试 / 无模型联调，**不产生语义向量**。

    用 SHA-256 把文本映射到固定维度的向量，满足：
    - 同一文本永远得到同一向量（幂等，方便写断言）；
    - 不同文本几乎不会碰撞（SHA-256 的均匀性）。
    但向量之间没有语义相似度，检索结果无意义。真实 RAG 必须换真实模型。
    """

    def __init__(self, dimension: int = settings.embedding_dim):
        self.dimension = dimension

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            vectors.append(self._embed_one(text))
        return vectors

    def _embed_one(self, text: str) -> list[float]:
        # 用 SHA-256 生成 32 字节，循环扩展到 dimension 维，再归一化到 [-1, 1]。
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        vector: list[float] = []
        for i in range(self.dimension):
            byte = digest[i % len(digest)]
            # 加一点点位置扰动，让不同维度位置不完全同值，避免向量退化成常数。
            vector.append(((byte / 127.5) - 1.0) + (i * 1e-4 % 1e-3))
        return vector


def get_embedding_service() -> EmbeddingService:
    """返回当前可用的 Embedding 服务。

    现阶段只有确定性桩。RH-19 在这里按 settings 切换：
    - 配置了 OPENAI_API_KEY / OPENAI_BASE_URL → OpenAI 兼容 embedding API
    - 否则 → 本地 BGE 模型（sentence-transformers / FlagEmbedding）
    """
    return DeterministicEmbedding(dimension=settings.embedding_dim)
