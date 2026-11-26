"""Embedding 服务（RH-19 补全真实后端）。

三种后端，都实现同一接口 EmbeddingService：
- LocalBgeEmbedding     本地 BGE 模型（sentence-transformers），默认，无需 API Key。
- OpenAICompatEmbedding OpenAI 兼容的 /embeddings API（httpx 直连），配 key + base_url 即用。
- DeterministicEmbedding 确定性哈希桩，仅测试 / 无模型联调，无语义。

向量维度必须与 Qdrant Collection 一致（RH-17 按 settings.embedding_dim=512 建库）。
换模型 = 换维度 = 要重建 Collection。
"""
from __future__ import annotations

import hashlib
import importlib.util
import logging
from abc import ABC, abstractmethod

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

__all__ = [
    "EmbeddingService",
    "LocalBgeEmbedding",
    "OpenAICompatEmbedding",
    "DeterministicEmbedding",
    "get_embedding_service",
]


class EmbeddingService(ABC):
    """把文本编码为向量的服务。所有后端都实现它。"""

    dimension: int

    @abstractmethod
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """把一批文本编码为向量，返回顺序与输入一致。"""
        raise NotImplementedError

    def embed_query(self, query: str) -> list[float]:
        """把检索 query 编码为单条向量。默认等价于 embed_texts，BGE 子类会加查询指令前缀。"""
        return self.embed_texts([query])[0]


# BGE 系列对短 query 推荐的指令前缀，能显著提升检索相关性。
BGE_QUERY_PREFIX = "为这个句子生成表示以用于检索相关文章："


class LocalBgeEmbedding(EmbeddingService):
    """本地 BGE 模型（sentence-transformers）。惰性加载：第一次 embed 才下载/加载模型。

    依赖：pip install sentence-transformers（会连带 torch）。
    模型名来自 settings.embedding_model，默认 BAAI/bge-small-zh-v1.5（512 维）。
    """

    def __init__(self, model_name: str | None = None, dimension: int | None = None):
        self._model_name = model_name or settings.embedding_model
        self._model = None
        self.dimension = dimension or settings.embedding_dim

    def _load(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:  # pragma: no cover - 环境相关
                raise RuntimeError(
                    "未安装 sentence-transformers，无法使用本地 BGE embedding。"
                    "请 pip install sentence-transformers，或改配 OPENAI_API_KEY 走兼容 API。"
                ) from exc
            self._model = SentenceTransformer(self._model_name)
        return self._model

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        model = self._load()
        vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return [v.tolist() for v in vectors]

    def embed_query(self, query: str) -> list[float]:
        # BGE 检索场景：query 侧加指令前缀，与「文档侧不加前缀」形成不对称编码，相关性更好。
        return self.embed_texts([BGE_QUERY_PREFIX + query])[0]


class OpenAICompatEmbedding(EmbeddingService):
    """OpenAI 兼容的 /embeddings API（用 httpx 直连，不额外引入 openai 包）。

    需要 settings.openai_api_key + settings.openai_base_url，模型名用 settings.embedding_model。
    兼容任意 OpenAI 协议服务（SiliconFlow / DashScope / vLLM / Ollama 的 embeddings 端点等）。
    """

    def __init__(self, dimension: int | None = None):
        self.dimension = dimension or settings.embedding_dim
        self._base_url = settings.openai_base_url.rstrip("/")
        self._api_key = settings.openai_api_key
        self._model = settings.embedding_model

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        resp = httpx.post(
            f"{self._base_url}/embeddings",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={"model": self._model, "input": texts},
            timeout=60.0,
        )
        resp.raise_for_status()
        data = resp.json()
        # OpenAI 协议返回 data[{embedding, index}]，按 index 排序保证与输入顺序一致。
        items = sorted(data["data"], key=lambda x: x["index"])
        vectors = [item["embedding"] for item in items]
        if vectors and self.dimension != len(vectors[0]):
            logger.warning(
                "API 返回维度 %s 与配置 embedding_dim=%s 不一致，检查 embedding_model",
                len(vectors[0]), self.dimension,
            )
        return vectors


class DeterministicEmbedding(EmbeddingService):
    """确定性哈希向量：仅用于测试 / 无模型联调，**不产生语义向量**。

    用 SHA-256 把文本映射到固定维度，同一文本永远同向量、不同文本几乎不碰撞。
    """

    def __init__(self, dimension: int = settings.embedding_dim):
        self.dimension = dimension

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    def _embed_one(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        vector: list[float] = []
        for i in range(self.dimension):
            byte = digest[i % len(digest)]
            vector.append(((byte / 127.5) - 1.0) + (i * 1e-4 % 1e-3))
        return vector


def _sentence_transformers_available() -> bool:
    return importlib.util.find_spec("sentence_transformers") is not None


def get_embedding_service() -> EmbeddingService:
    """按 settings 选择可用的 Embedding 后端。

    优先级：OpenAI 兼容 API（配了 key+base_url）> 本地 BGE（装了 sentence-transformers）
    > 确定性桩（测试/联调，无语义）。
    """
    if settings.openai_api_key and settings.openai_base_url:
        return OpenAICompatEmbedding()
    if _sentence_transformers_available():
        return LocalBgeEmbedding()
    logger.warning("未配置真实 embedding，回退到确定性桩（无语义，仅用于打通链路）")
    return DeterministicEmbedding()
