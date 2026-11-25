"""个人菜谱接口：CRUD + 一键导入（RH-07 业务实现）。

每个接口先 get_or_create_user 把请求头里的 openid 映射到 users.id，
再由 service 按 owner_id 隔离操作，确保只能访问自己的菜谱。
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_id
from app.db.session import get_db
from app.schemas import (
    RecipeCreate,
    RecipeImportRequest,
    RecipeImportResponse,
    RecipeRead,
    RecipeUpdate,
)
from app.services.recipe import service

router = APIRouter(prefix="/api/recipes", tags=["recipes"])


@router.get("", response_model=list[RecipeRead], summary="获取当前用户个人菜谱列表")
def list_recipes(
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
    openid: str = Depends(get_current_user_id),
) -> list[RecipeRead]:
    user = service.get_or_create_user(db, openid)
    return service.list_user_recipes(db, user, skip, limit)


@router.post("", response_model=RecipeRead, status_code=status.HTTP_201_CREATED, summary="创建个人菜谱")
def create_recipe(
    payload: RecipeCreate,
    db: Session = Depends(get_db),
    openid: str = Depends(get_current_user_id),
) -> RecipeRead:
    user = service.get_or_create_user(db, openid)
    return service.create_recipe(db, user, payload)


@router.get("/{recipe_id}", response_model=RecipeRead, summary="获取菜谱详情")
def get_recipe(
    recipe_id: int,
    db: Session = Depends(get_db),
    openid: str = Depends(get_current_user_id),
) -> RecipeRead:
    user = service.get_or_create_user(db, openid)
    return service.get_user_recipe(db, user, recipe_id)


@router.put("/{recipe_id}", response_model=RecipeRead, summary="更新菜谱")
def update_recipe(
    recipe_id: int,
    payload: RecipeUpdate,
    db: Session = Depends(get_db),
    openid: str = Depends(get_current_user_id),
) -> RecipeRead:
    user = service.get_or_create_user(db, openid)
    return service.update_recipe(db, user, recipe_id, payload)


@router.delete("/{recipe_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除菜谱")
def delete_recipe(
    recipe_id: int,
    db: Session = Depends(get_db),
    openid: str = Depends(get_current_user_id),
) -> None:
    user = service.get_or_create_user(db, openid)
    service.delete_recipe(db, user, recipe_id)


@router.post("/import", response_model=RecipeImportResponse, summary="从公共菜谱导入个人厨房")
def import_recipe(
    payload: RecipeImportRequest,
    db: Session = Depends(get_db),
    openid: str = Depends(get_current_user_id),
) -> RecipeImportResponse:
    user = service.get_or_create_user(db, openid)
    recipe = service.import_recipe(db, user, payload.source_recipe_id)
    return RecipeImportResponse(recipe_id=recipe.id)
