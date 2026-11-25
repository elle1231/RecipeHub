"""公共菜谱接口：分页列表 + 关键词搜索 + 分类/菜系筛选 + 详情（RH-08）。

公共菜谱是 `owner_id IS NULL` 的 recipes，与个人菜谱共用一张表；
这里只暴露公共菜谱，绝不会把个人菜谱漏出去。
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas import RecipeRead
from app.services.recipe import public_service

router = APIRouter(prefix="/api/public-recipes", tags=["public-recipes"])


@router.get("", response_model=list[RecipeRead], summary="浏览公共菜谱（分页 + 搜索 + 筛选）")
def list_public_recipes(
    skip: int = 0,
    limit: int = 20,
    q: str | None = None,
    category: str | None = None,
    cuisine: str | None = None,
    db: Session = Depends(get_db),
) -> list[RecipeRead]:
    return public_service.list_public_recipes(db, skip, limit, q=q, category=category, cuisine=cuisine)


@router.get("/{recipe_id}", response_model=RecipeRead, summary="获取公共菜谱详情")
def get_public_recipe(recipe_id: int, db: Session = Depends(get_db)) -> RecipeRead:
    return public_service.get_public_recipe(db, recipe_id)
