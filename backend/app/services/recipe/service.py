"""个人菜谱业务逻辑：CRUD + 一键导入（RH-07）。

所有操作都按 owner_id 隔离——用户只能看到/改/删自己的菜谱；
导入把公共菜谱复制成个人副本（status=Imported + source_recipe_id 溯源）。
"""
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Recipe, RecipeIngredient, RecipeStep, User
from app.schemas import RecipeCreate, RecipeUpdate
from app.services.user.service import get_or_create_user

__all__ = [
    "get_or_create_user",
    "list_user_recipes",
    "create_recipe",
    "get_user_recipe",
    "update_recipe",
    "delete_recipe",
    "import_recipe",
]


# ---------- 内部工具 ----------

def _build_ingredients(items) -> list[RecipeIngredient]:
    """把食材（Schema 或 ORM 对象）转成新的 RecipeIngredient 列表。"""
    return [
        RecipeIngredient(
            sort_order=item.sort_order,
            ingredient_name=item.ingredient_name,
            quantity=item.quantity,
            unit=item.unit,
            optional_note=item.optional_note,
        )
        for item in items
    ]


def _build_steps(items) -> list[RecipeStep]:
    """把步骤（Schema 或 ORM 对象）转成新的 RecipeStep 列表。"""
    return [
        RecipeStep(
            step_number=item.step_number,
            instruction=item.instruction,
            heat_level=item.heat_level,
            duration_minutes=item.duration_minutes,
        )
        for item in items
    ]


def _get_owned_recipe(db: Session, user: User, recipe_id: int) -> Recipe:
    """取「属于当前用户」的菜谱；不存在或不属于当前用户都返回 404。

    统一返回 404 而不是 403，避免通过状态码差异泄露「他人的菜谱是否存在」。
    """
    recipe = db.get(Recipe, recipe_id)
    if recipe is None or recipe.owner_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="菜谱不存在或无权访问"
        )
    return recipe


# ---------- 对外服务 ----------

def list_user_recipes(db: Session, user: User, skip: int, limit: int) -> list[Recipe]:
    """当前用户个人菜谱列表，按更新时间倒序。"""
    stmt = (
        select(Recipe)
        .where(Recipe.owner_id == user.id)
        .order_by(Recipe.updated_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return list(db.scalars(stmt).all())


def create_recipe(db: Session, user: User, payload: RecipeCreate) -> Recipe:
    """创建个人菜谱。默认 status=Draft、visibility=private、orderable=False。"""
    recipe = Recipe(
        owner_id=user.id,
        title=payload.title,
        description=payload.description,
        image_url=payload.image_url,
        category=payload.category,
        cuisine=payload.cuisine,
        cooking_time=payload.cooking_time,
        difficulty=payload.difficulty,
        status="Draft",
        visibility="private",
        orderable=False,
        current_version=1,
    )
    recipe.ingredients = _build_ingredients(payload.ingredients)
    recipe.steps = _build_steps(payload.steps)
    db.add(recipe)
    db.commit()
    return recipe


def get_user_recipe(db: Session, user: User, recipe_id: int) -> Recipe:
    """菜谱详情（含食材/步骤）。"""
    return _get_owned_recipe(db, user, recipe_id)


def update_recipe(db: Session, user: User, recipe_id: int, payload: RecipeUpdate) -> Recipe:
    """部分更新：只改传入的字段；ingredients/steps 传了则整体替换，不传则不变。"""
    recipe = _get_owned_recipe(db, user, recipe_id)

    # 标量字段：用 model_dump(exclude_unset=True) 只拿「本次显式传入」的字段。
    # 嵌套字段不 dump（dump 会把 Pydantic 子模型变成 dict），直接读原始对象。
    data = payload.model_dump(exclude_unset=True, exclude={"ingredients", "steps"})
    for field, value in data.items():
        setattr(recipe, field, value)

    if payload.ingredients is not None:
        recipe.ingredients = _build_ingredients(payload.ingredients)
    if payload.steps is not None:
        recipe.steps = _build_steps(payload.steps)

    db.commit()
    return recipe


def delete_recipe(db: Session, user: User, recipe_id: int) -> None:
    """删除个人菜谱（级联删除其食材/步骤）。"""
    recipe = _get_owned_recipe(db, user, recipe_id)
    db.delete(recipe)
    db.commit()


def import_recipe(db: Session, user: User, source_recipe_id: int) -> Recipe:
    """把公共菜谱复制成当前用户的个人副本。

    流程（对应 PLAN 11.1）：
    1. 校验公共菜谱存在（owner_id 为空才叫「公共菜谱」）。
    2. 校验当前用户未导入过（owner_id + source_recipe_id 去重）。
    3. 复制主信息、食材、步骤；写 source_recipe_id；status=Imported。
    """
    source = db.get(Recipe, source_recipe_id)
    if source is None or source.owner_id is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="公共菜谱不存在")

    existing = db.scalar(
        select(Recipe).where(
            Recipe.owner_id == user.id,
            Recipe.source_recipe_id == source_recipe_id,
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"该菜谱已导入过（个人菜谱 id={existing.id}），无需重复导入",
        )

    recipe = Recipe(
        owner_id=user.id,
        source_recipe_id=source.id,
        title=source.title,
        description=source.description,
        image_url=source.image_url,
        category=source.category,
        cuisine=source.cuisine,
        cooking_time=source.cooking_time,
        difficulty=source.difficulty,
        status="Imported",
        visibility="private",
        orderable=False,
        current_version=1,
    )
    recipe.ingredients = _build_ingredients(source.ingredients)
    recipe.steps = _build_steps(source.steps)
    db.add(recipe)
    db.commit()
    return recipe
