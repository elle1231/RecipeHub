"""用户与饮食画像模型。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, utcnow


class User(Base):
    """用户。本地演示阶段用 openid 存测试用户 ID。"""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    openid: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    nickname: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    # 一对一画像
    profile: Mapped["UserProfile | None"] = relationship(back_populates="user", uselist=False)
    # 该用户创建的个人菜谱（公共菜谱的 owner 为空）
    recipes: Mapped[list["Recipe"]] = relationship(back_populates="owner")


class UserProfile(Base):
    """用户长期饮食画像（每个用户至多一条）。"""

    __tablename__ = "user_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True, nullable=False)

    dietary_goal: Mapped[str | None] = mapped_column(String(64))            # 增肌 / 减脂 / 均衡饮食
    taste_preferences: Mapped[list | None] = mapped_column(JSON)             # ["清淡", "微辣"]
    disliked_ingredients: Mapped[list | None] = mapped_column(JSON)          # ["香菜", "胡萝卜"]
    allergens: Mapped[list | None] = mapped_column(JSON)                     # ["花生", "虾"]
    dietary_habits: Mapped[list | None] = mapped_column(JSON)                # ["高蛋白", "少油"]
    max_cooking_time: Mapped[int | None] = mapped_column(Integer)            # 分钟
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    user: Mapped["User"] = relationship(back_populates="profile")
