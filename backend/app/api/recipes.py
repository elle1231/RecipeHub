"""个人菜谱接口。

第一版契约（Day 1）：这里只定义路由、请求/响应结构，不写业务。
业务逻辑（CRUD、一键导入）在 Day 2 的 service 层实现，届时替换每个 501。
"""
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user_id
from app.schemas import (
    RecipeCreate,
    RecipeImportRequest,
    RecipeImportResponse,
    RecipeRead,
    RecipeUpdate,
)

router = APIRouter(prefix="/api/recipes", tags=["recipes"])

_NOT_IMPLEMENTED = "接口契约已定义，业务逻辑在 Day 2 (RH-07) 实现"


@router.get("", response_model=list[RecipeRead], summary="获取当前用户个人菜谱列表")
def list_recipes(
    skip: int = 0,
    limit: int = 20,
    user_id: str = Depends(get_current_user_id),
) -> list[RecipeRead]:
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=_NOT_IMPLEMENTED)


@router.post("", response_model=RecipeRead, status_code=status.HTTP_201_CREATED, summary="创建个人菜谱")
def create_recipe(payload: RecipeCreate, user_id: str = Depends(get_current_user_id)) -> RecipeRead:
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=_NOT_IMPLEMENTED)


@router.get("/{recipe_id}", response_model=RecipeRead, summary="获取菜谱详情")
def get_recipe(recipe_id: int, user_id: str = Depends(get_current_user_id)) -> RecipeRead:
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=_NOT_IMPLEMENTED)


@router.put("/{recipe_id}", response_model=RecipeRead, summary="更新菜谱")
def update_recipe(
    recipe_id: int, payload: RecipeUpdate, user_id: str = Depends(get_current_user_id)
) -> RecipeRead:
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=_NOT_IMPLEMENTED)


@router.delete("/{recipe_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除菜谱")
def delete_recipe(recipe_id: int, user_id: str = Depends(get_current_user_id)) -> None:
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=_NOT_IMPLEMENTED)


@router.post("/import", response_model=RecipeImportResponse, summary="从公共菜谱导入个人厨房")
def import_recipe(
    payload: RecipeImportRequest, user_id: str = Depends(get_current_user_id)
) -> RecipeImportResponse:
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=_NOT_IMPLEMENTED)
