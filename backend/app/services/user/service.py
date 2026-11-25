"""用户相关服务：身份映射 + 饮食画像（RH-09）。

本地演示阶段用 openid 标识用户；openid → users.id 的映射在这里完成。
画像采用「首次读写即建行」的 lazy 策略：GET/PUT 都先 get_or_create，
保证每个用户至多一条 user_profiles，且读取无画像时也能拿到合法空画像。
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User, UserProfile
from app.schemas import UserProfileUpdate

__all__ = [
    "get_or_create_user",
    "get_or_create_profile",
    "get_profile",
    "update_profile",
]


def get_or_create_user(db: Session, openid: str) -> User:
    """按 openid 取用户；不存在则创建并返回已持久化的 User。

    这是 deps.get_current_user_id（返回 openid）到 users.id 的桥接点：
    recipes.owner_id 等外键指向 users.id（整数），而请求头里只有 openid（字符串）。
    """
    user = db.scalar(select(User).where(User.openid == openid))
    if user is None:
        user = User(openid=openid, nickname=openid)
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def get_or_create_profile(db: Session, user: User) -> UserProfile:
    """取用户画像；不存在则建一条空画像（所有偏好字段为 NULL）。

    user_profiles.user_id 有唯一约束，保证每个用户至多一条。
    """
    profile = db.scalar(select(UserProfile).where(UserProfile.user_id == user.id))
    if profile is None:
        profile = UserProfile(user_id=user.id)
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return profile


def get_profile(db: Session, user: User) -> UserProfile:
    """读取饮食画像（无画像时返回一条空画像，前端可据此渲染空表单）。"""
    return get_or_create_profile(db, user)


def update_profile(db: Session, user: User, payload: UserProfileUpdate) -> UserProfile:
    """部分更新画像：只改本次显式传入的字段，未传的保持原值。"""
    profile = get_or_create_profile(db, user)

    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(profile, field, value)

    db.commit()
    return profile
