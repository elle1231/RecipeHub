"""AI 菜单规划模型。

菜单规划是多轮交互的核心，状态必须持久化到 SQLite，
不能只放在前端内存里（否则刷新/重启就丢）。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, utcnow


class Menu(Base):
    """一次菜单规划会话（多轮状态机）。"""

    __tablename__ = "menus"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)

    requirements_json: Mapped[dict | None] = mapped_column(JSON)        # 结构化需求（人数/预算/口味等）
    confirmed_dishes_json: Mapped[list | None] = mapped_column(JSON)    # 已确认菜品
    rejected_dishes_json: Mapped[list | None] = mapped_column(JSON)     # 已拒绝菜品
    candidates_json: Mapped[list | None] = mapped_column(JSON)          # 当前候选菜品

    # status: draft / awaiting_confirmation / confirmed / completed
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    user: Mapped["User"] = relationship()
    drafts: Mapped[list["MenuRecipeDraft"]] = relationship(back_populates="menu")


class MenuRecipeDraft(Base):
    """AI 新生成的菜谱草稿，与某个菜单关联。

    推荐/确认一道菜 ≠ 用户做过。只有用户实际制作并确认后，
    才允许 promote 到个人厨房（promoted_recipe_id 指向正式菜谱）。
    """

    __tablename__ = "menu_recipe_drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    menu_id: Mapped[int] = mapped_column(ForeignKey("menus.id"), index=True, nullable=False)
    generated_recipe_json: Mapped[dict | None] = mapped_column(JSON)     # AI 生成的完整菜谱结构
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)
    promoted_recipe_id: Mapped[int | None] = mapped_column(ForeignKey("recipes.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    menu: Mapped["Menu"] = relationship(back_populates="drafts")
    promoted_recipe: Mapped["Recipe | None"] = relationship()
