"""用户与饮食画像接口：画像读取 + 更新（RH-09 业务实现）。

画像与用户一对一，首次读写自动建行；更新是部分更新（只改传入字段）。
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_id
from app.db.session import get_db
from app.schemas import UserProfileRead, UserProfileUpdate
from app.services.user import service

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("/profile", response_model=UserProfileRead, summary="获取饮食画像")
def get_profile(
    db: Session = Depends(get_db),
    openid: str = Depends(get_current_user_id),
) -> UserProfileRead:
    user = service.get_or_create_user(db, openid)
    return service.get_profile(db, user)


@router.put("/profile", response_model=UserProfileRead, summary="更新饮食画像")
def update_profile(
    payload: UserProfileUpdate,
    db: Session = Depends(get_db),
    openid: str = Depends(get_current_user_id),
) -> UserProfileRead:
    user = service.get_or_create_user(db, openid)
    return service.update_profile(db, user, payload)
