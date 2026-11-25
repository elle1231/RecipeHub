"""菜谱、食材、步骤、版本、制作记录模型。

菜谱是核心实体：
- 公共菜谱：owner_id 为空，source_recipe_id 也为空。
- 个人菜谱：owner_id 指向创建它的用户。
- 导入菜谱：owner_id 指向导入用户，source_recipe_id 指向原公共菜谱。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, utcnow


class Recipe(Base):
    """菜谱主表。status / visibility / orderable 三者独立，互不混合。"""

    __tablename__ = "recipes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True, nullable=True)
    source_recipe_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 导入自哪个公共菜谱
    source: Mapped[str | None] = mapped_column(String(500))  # 公共菜谱数据来源（如 HowToCook 文件路径），用于溯源/授权，与 source_recipe_id 无关

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(String(500))
    category: Mapped[str | None] = mapped_column(String(64))
    cuisine: Mapped[str | None] = mapped_column(String(64))
    cooking_time: Mapped[int | None] = mapped_column(Integer)      # 分钟
    difficulty: Mapped[str | None] = mapped_column(String(32))

    # status: Draft / Imported / Cooked / Verified
    status: Mapped[str] = mapped_column(String(32), default="Draft", nullable=False)
    # visibility: private / public
    visibility: Mapped[str] = mapped_column(String(32), default="private", nullable=False)
    orderable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    current_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    owner: Mapped["User | None"] = relationship(back_populates="recipes")
    ingredients: Mapped[list["RecipeIngredient"]] = relationship(
        back_populates="recipe", cascade="all, delete-orphan", order_by="RecipeIngredient.sort_order"
    )
    steps: Mapped[list["RecipeStep"]] = relationship(
        back_populates="recipe", cascade="all, delete-orphan", order_by="RecipeStep.step_number"
    )
    versions: Mapped[list["RecipeVersion"]] = relationship(back_populates="recipe")
    cooking_records: Mapped[list["CookingRecord"]] = relationship(back_populates="recipe")


class RecipeIngredient(Base):
    """菜谱食材。quantity 用字符串以兼容「适量」「少许」「500克」等表达。"""

    __tablename__ = "recipe_ingredients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id"), index=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ingredient_name: Mapped[str] = mapped_column(String(100), nullable=False)
    quantity: Mapped[str | None] = mapped_column(String(50))
    unit: Mapped[str | None] = mapped_column(String(32))
    optional_note: Mapped[str | None] = mapped_column(String(200))

    recipe: Mapped["Recipe"] = relationship(back_populates="ingredients")


class RecipeStep(Base):
    """菜谱烹饪步骤（有序）。"""

    __tablename__ = "recipe_steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id"), index=True, nullable=False)
    step_number: Mapped[int] = mapped_column(Integer, nullable=False)
    instruction: Mapped[str] = mapped_column(Text, nullable=False)
    heat_level: Mapped[str | None] = mapped_column(String(32))     # 大火/中火/小火
    duration_minutes: Mapped[int | None] = mapped_column(Integer)

    recipe: Mapped["Recipe"] = relationship(back_populates="steps")


class RecipeVersion(Base):
    """菜谱版本快照。不覆盖原记录，保留父子关系。"""

    __tablename__ = "recipe_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id"), index=True, nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    change_note: Mapped[str | None] = mapped_column(String(500))
    snapshot_json: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    recipe: Mapped["Recipe"] = relationship(back_populates="versions")


class CookingRecord(Base):
    """制作记录：用户实际做一次之后的反馈，是个性化推荐与 RAG 的数据来源。"""

    __tablename__ = "cooking_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id"), index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)

    actual_ingredients_json: Mapped[list | None] = mapped_column(JSON)
    actual_steps: Mapped[str | None] = mapped_column(Text)
    rating: Mapped[int | None] = mapped_column(Integer)
    problems: Mapped[str | None] = mapped_column(Text)
    next_time_adjustment: Mapped[str | None] = mapped_column(Text)
    photo_url: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    recipe: Mapped["Recipe"] = relationship(back_populates="cooking_records")
    user: Mapped["User"] = relationship()
