"""公共菜谱接口。

契约（Day 1）：公共菜谱列表 + 详情。搜索、分类筛选在 Day 2 补充。
"""
from fastapi import APIRouter, HTTPException, status

from app.schemas import RecipeRead

router = APIRouter(prefix="/api/public-recipes", tags=["public-recipes"])

_NOT_IMPLEMENTED = "接口契约已定义，业务逻辑在 Day 2 (RH-08) 实现"


@router.get("", response_model=list[RecipeRead], summary="浏览公共菜谱（分页）")
def list_public_recipes(skip: int = 0, limit: int = 20) -> list[RecipeRead]:
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=_NOT_IMPLEMENTED)


@router.get("/{recipe_id}", response_model=RecipeRead, summary="获取公共菜谱详情")
def get_public_recipe(recipe_id: int) -> RecipeRead:
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=_NOT_IMPLEMENTED)
