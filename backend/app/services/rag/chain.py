"""基础 RAG Chain（RH-21）。

流程（PLAN Day3 任务6）：
问题 → 检索公共 + 个人（RH-20）→ 合并去重 → 构建带来源上下文 → 调用 LLM → 返回回答 + 引用。

关键约束：检索为空时**不调用 LLM**，直接返回「没有找到相关内容」+ 空 sources，
绝不伪造来源。
"""
from __future__ import annotations

from qdrant_client import QdrantClient

from app.schemas.rag import RagAskResponse
from app.services.rag.embedding import EmbeddingService
from app.services.rag.llm import LLMService
from app.services.rag.retrieval import RetrievedChunk, search

__all__ = ["build_context", "rag_answer"]

_SYSTEM_PROMPT = (
    "你是 RecipeHub 的厨房助手。请只依据下面提供的资料回答用户问题，"
    "不要编造资料中没有的内容；如果资料不足以回答，请明确说明。"
    "回答时可以用【来源N】标注你的依据。"
)

_COLLECTION_LABEL = {
    "public_recipes": "公共菜谱",
    "personal_kitchens": "个人厨房",
}

# 相关度阈值（余弦相似度）：低于此分数视为「未检索到相关内容」，不喂给 LLM。
# 实测（BGE-small-zh-v1.5 + 余弦）：相关查询 top1 ≈ 0.55~0.69，无关查询 ≈ 0.24~0.28。
# 0.45 落在两者中间，换模型需按新模型的分数分布重调。
MIN_SCORE = 0.45


def build_context(chunks: list[RetrievedChunk]) -> str:
    """把检索命中的 chunk 拼成带编号来源的上下文，供 LLM 引用。"""
    parts = []
    for i, c in enumerate(chunks, 1):
        label = _COLLECTION_LABEL.get(c.collection, c.collection)
        parts.append(f"【来源{i}】{c.title}（{label}）\n{c.content}")
    return "\n\n".join(parts)


def rag_answer(
    client: QdrantClient,
    embedder: EmbeddingService,
    llm: LLMService,
    question: str,
    user_id: int,
    public_limit: int = 5,
    personal_limit: int = 5,
) -> RagAskResponse:
    """执行一次 RAG 问答：检索 → 上下文 → LLM → 回答 + 来源。"""
    result = search(client, embedder, question, user_id, public_limit, personal_limit)
    merged = result["merged"]

    # 只保留高于阈值的命中；低于阈值视为「没找到相关内容」。
    relevant = [c for c in merged if c.score >= MIN_SCORE]
    if not relevant:
        return RagAskResponse(answer="抱歉，没有找到与问题相关的内容。", sources=[])

    merged = relevant

    context = build_context(merged)
    user_prompt = f"参考资料：\n{context}\n\n用户问题：{question}"
    answer = llm.generate(
        [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
    )
    return RagAskResponse(answer=answer, sources=merged)
