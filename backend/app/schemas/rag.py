"""RAG 问答的请求/响应 Schema（RH-21）。"""
from pydantic import BaseModel, Field

from app.services.rag.retrieval import RetrievedChunk


class RagAskRequest(BaseModel):
    """RAG 问答请求。question 是用户要问的烹饪/菜谱问题。"""

    question: str = Field(..., min_length=1, max_length=500)


class RagAskResponse(BaseModel):
    """RAG 问答响应：answer 是 LLM 回答，sources 是引用的检索来源。"""

    answer: str
    sources: list[RetrievedChunk] = []
