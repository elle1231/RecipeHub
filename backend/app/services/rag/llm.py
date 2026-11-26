"""LLM 服务（RH-21）。

基础版只提供 OpenAI 兼容的 chat completion（用 httpx 直连，不额外引入 openai 包）。
RAG Chain 依赖它生成回答；未配置时 `get_llm_service()` 返回 None，API 层据此返回 503。
"""
from __future__ import annotations

from abc import ABC, abstractmethod

import httpx

from app.core.config import settings

__all__ = ["LLMService", "OpenAICompatLLM", "get_llm_service"]


class LLMService(ABC):
    """对话生成服务。输入 messages（OpenAI chat 格式），返回回复文本。"""

    @abstractmethod
    def generate(self, messages: list[dict]) -> str:
        raise NotImplementedError


class OpenAICompatLLM(LLMService):
    """OpenAI 兼容的 /chat/completions（httpx 直连）。

    需要 settings.openai_api_key + openai_base_url + llm_model。
    兼容任意 OpenAI 协议服务（vLLM / Ollama / 各类云 API）。
    """

    def __init__(self):
        self._base_url = settings.openai_base_url.rstrip("/")
        self._api_key = settings.openai_api_key
        self._model = settings.llm_model

    def generate(self, messages: list[dict]) -> str:
        resp = httpx.post(
            f"{self._base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={"model": self._model, "messages": messages, "temperature": 0.3},
            timeout=60.0,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


def get_llm_service() -> LLMService | None:
    """按 settings 返回可用 LLM；未配置则返回 None（调用方需给出明确反馈）。"""
    if settings.openai_api_key and settings.openai_base_url and settings.llm_model:
        return OpenAICompatLLM()
    return None
