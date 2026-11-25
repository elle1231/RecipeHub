"""公共菜谱业务逻辑：分页列表 + 详情 + 关键词搜索 + 分类/菜系筛选（RH-08）。

公共菜谱与个人菜谱共用 `recipes` 表，区别只在于 `owner_id IS NULL`。
所以这里所有查询都强制 `owner_id IS NULL`，个人菜谱不会漏进菜谱大全，
公共接口也不会把任何个人菜谱暴露出去。
"""
from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import Recipe

__all__ = ["list_public_recipes", "get_public_recipe"]


def list_public_recipes(
    db: Session,
    skip: int,
    limit: int,
    q: str | None = None,
    category: str | None = None,
    cuisine: str | None = None,
) -> list[Recipe]:
    """公共菜谱分页列表，支持关键词（标题/描述）与分类、菜系筛选。"""
    stmt = select(Recipe).where(Recipe.owner_id.is_(None))

    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(
            or_(Recipe.title.like(pattern), Recipe.description.like(pattern))
        )
    if category:
        stmt = stmt.where(Recipe.category == category)
    if cuisine:
        stmt = stmt.where(Recipe.cuisine == cuisine)

    stmt = stmt.order_by(Recipe.id.desc()).offset(skip).limit(limit)
    return list(db.scalars(stmt).all())


def get_public_recipe(db: Session, recipe_id: int) -> Recipe:
    """公共菜谱详情（含食材/步骤）；不存在或是个人菜谱都返回 404。"""
    recipe = db.get(Recipe, recipe_id)
    if recipe is None or recipe.owner_id is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="公共菜谱不存在"
        )
    return recipe
