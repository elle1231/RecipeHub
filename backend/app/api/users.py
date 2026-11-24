"""用户与饮食画像接口。

契约（Day 1）：画像读取 + 更新。业务逻辑在 Day 2 实现。
"""
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user_id
from app.schemas import UserProfileRead, UserProfileUpdate

router = APIRouter(prefix="/api/users", tags=["users"])

_NOT_IMPLEMENTED = "接口契约已定义，业务逻辑在 Day 2 (RH-09) 实现"


@router.get("/profile", response_model=UserProfileRead, summary="获取饮食画像")
def get_profile(user_id: str = Depends(get_current_user_id)) -> UserProfileRead:
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=_NOT_IMPLEMENTED)


@router.put("/profile", response_model=UserProfileRead, summary="更新饮食画像")
def update_profile(
    payload: UserProfileUpdate, user_id: str = Depends(get_current_user_id)
) -> UserProfileRead:
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=_NOT_IMPLEMENTED)
