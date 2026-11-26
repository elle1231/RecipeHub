"""RAG 问答接口（RH-21）。

POST /api/rag/ask  接收问题 → 检索公共+个人 → LLM 回答 + 引用来源。
user_id 由后端从 openid 解析，绝不来自请求体，保证个人知识隔离。
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_id
from app.db.qdrant import get_qdrant_client
from app.db.session import get_db
from app.schemas import RagAskRequest, RagAskResponse
from app.services.rag.chain import rag_answer
from app.services.rag.embedding import get_embedding_service
from app.services.rag.llm import get_llm_service
from app.services.user.service import get_or_create_user

router = APIRouter(prefix="/api/rag", tags=["rag"])


@router.post("/ask", response_model=RagAskResponse, summary="基于知识库的 RAG 问答")
def ask(
    payload: RagAskRequest,
    db: Session = Depends(get_db),
    openid: str = Depends(get_current_user_id),
) -> RagAskResponse:
    # openid → 内部 users.id：user_id 由后端解析，客户端无法指定他人 id。
    user = get_or_create_user(db, openid)

    llm = get_llm_service()
    if llm is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM 未配置，请设置 OPENAI_API_KEY / OPENAI_BASE_URL / LLM_MODEL",
        )

    return rag_answer(
        get_qdrant_client(),
        get_embedding_service(),
        llm,
        payload.question,
        user.id,
    )
