"""RH-21 基础 RAG Chain 的单元测试。

用 monkeypatch 替换检索函数 + mock LLM，验证：
- 有检索结果时构建上下文、调用 LLM、返回回答 + 来源；
- 检索为空时不调 LLM、不伪造来源；
- LLM 未配置时工厂返回 None，API 返回 503。
"""
from unittest.mock import MagicMock

from app.core.config import settings
from app.schemas.rag import RagAskResponse
from app.services.rag import chain
from app.services.rag.chain import build_context, rag_answer
from app.services.rag.llm import OpenAICompatLLM, get_llm_service
from app.services.rag.retrieval import RetrievedChunk


def _chunk(doc_id, title, content, collection="public_recipes", score=0.8):
    return RetrievedChunk(
        document_id=doc_id, score=score, title=title, content=content,
        document_type="recipe", collection=collection,
    )


def test_build_context_numbers_sources():
    chunks = [
        _chunk("public_recipe_1#0", "番茄炒蛋", "食材：番茄、鸡蛋"),
        _chunk("personal_recipe_3_170#0", "我的鸡蛋羹", "少放盐", collection="personal_kitchens"),
    ]
    ctx = build_context(chunks)
    assert "【来源1】番茄炒蛋（公共菜谱）" in ctx
    assert "【来源2】我的鸡蛋羹（个人厨房）" in ctx
    assert "食材：番茄、鸡蛋" in ctx and "少放盐" in ctx


def test_rag_answer_with_hits_calls_llm(monkeypatch):
    chunks = [_chunk("public_recipe_1#0", "番茄炒蛋", "正文")]
    monkeypatch.setattr(chain, "search", lambda *a, **k: {"merged": chunks})

    llm = MagicMock()
    llm.generate.return_value = "番茄炒蛋的做法是：先炒蛋再下番茄。"

    resp = rag_answer(None, None, llm, "番茄炒蛋怎么做", user_id=1)

    assert resp.answer == "番茄炒蛋的做法是：先炒蛋再下番茄。"
    assert len(resp.sources) == 1
    assert resp.sources[0].title == "番茄炒蛋"
    llm.generate.assert_called_once()
    # 上下文确实喂给了 LLM
    messages = llm.generate.call_args.args[0]
    user_msg = messages[-1]["content"]
    assert "番茄炒蛋" in user_msg and "番茄炒蛋怎么做" in user_msg


def test_rag_answer_empty_retrieval_does_not_call_llm(monkeypatch):
    monkeypatch.setattr(chain, "search", lambda *a, **k: {"merged": []})
    llm = MagicMock()

    resp = rag_answer(None, None, llm, "不存在的问题", user_id=1)

    assert "没有找到" in resp.answer
    assert resp.sources == []
    llm.generate.assert_not_called()


def test_rag_answer_low_score_is_treated_as_no_content(monkeypatch):
    # 命中但低于阈值：同样视为「没找到」，不喂给 LLM、不伪造来源。
    low = _chunk("public_recipe_1#0", "无关菜", "无关内容", score=0.1)
    monkeypatch.setattr(chain, "search", lambda *a, **k: {"merged": [low]})
    llm = MagicMock()

    resp = rag_answer(None, None, llm, "无关问题", user_id=1)

    assert "没有找到" in resp.answer
    assert resp.sources == []
    llm.generate.assert_not_called()


def test_get_llm_service_returns_none_without_config(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "")
    assert get_llm_service() is None


def test_get_llm_service_returns_llm_with_config(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "k")
    monkeypatch.setattr(settings, "openai_base_url", "http://localhost:8000/v1")
    monkeypatch.setattr(settings, "llm_model", "gpt-test")
    svc = get_llm_service()
    assert isinstance(svc, OpenAICompatLLM)


def test_rag_ask_endpoint_returns_503_without_llm(client, monkeypatch):
    # 与真实 .env 是否配了 LLM 无关：直接 mock 工厂返回 None，验证 503 路径。
    import app.api.rag as rag_api

    monkeypatch.setattr(rag_api, "get_llm_service", lambda: None)
    resp = client.post("/api/rag/ask", json={"question": "番茄炒蛋怎么做"})
    assert resp.status_code == 503
