"""菜谱相关请求/响应 Schema。

这是第一版 API 契约的「数据形状」：字段、类型、必填项都在这里定死，
FastAPI 据此做请求校验并生成 OpenAPI 文档。业务实现（Day 2）直接复用。
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# ---------- 食材 / 步骤 ----------

class RecipeIngredientCreate(BaseModel):
    """创建菜谱时的一条食材。quantity 用字符串以兼容「适量」「500克」。"""

    ingredient_name: str = Field(..., max_length=100)
    quantity: str | None = None
    unit: str | None = None
    optional_note: str | None = None
    sort_order: int = 0


class RecipeIngredientRead(RecipeIngredientCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int


class RecipeStepCreate(BaseModel):
    """创建菜谱时的一条步骤。"""

    step_number: int
    instruction: str
    heat_level: str | None = None
    duration_minutes: int | None = None


class RecipeStepRead(RecipeStepCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int


# ---------- 菜谱主信息 ----------

class RecipeBase(BaseModel):
    title: str = Field(..., max_length=200)
    description: str | None = None
    image_url: str | None = None
    category: str | None = None
    cuisine: str | None = None
    cooking_time: int | None = None
    difficulty: str | None = None


class RecipeCreate(RecipeBase):
    """创建菜谱请求。食材和步骤随主信息一起提交。"""

    ingredients: list[RecipeIngredientCreate] = []
    steps: list[RecipeStepCreate] = []


class RecipeUpdate(BaseModel):
    """更新菜谱请求。全字段可选，未传的字段保持原值（部分更新）。

    ingredients / steps 传了则整体替换，不传则不变（Day 2 实现该语义）。
    """

    title: str | None = None
    description: str | None = None
    image_url: str | None = None
    category: str | None = None
    cuisine: str | None = None
    cooking_time: int | None = None
    difficulty: str | None = None
    status: str | None = None
    visibility: str | None = None
    orderable: bool | None = None
    ingredients: list[RecipeIngredientCreate] | None = None
    steps: list[RecipeStepCreate] | None = None


class RecipeRead(RecipeBase):
    """菜谱详情响应。个人菜谱和公共菜谱复用同一结构。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int | None = None
    source_recipe_id: int | None = None
    status: str
    visibility: str
    orderable: bool
    current_version: int
    created_at: datetime
    updated_at: datetime
    ingredients: list[RecipeIngredientRead] = []
    steps: list[RecipeStepRead] = []


# ---------- 一键导入 ----------

class RecipeImportRequest(BaseModel):
    """从公共菜谱导入个人厨房的请求。"""

    source_recipe_id: int


class RecipeImportResponse(BaseModel):
    """导入成功后返回新建个人菜谱的 id。"""

    recipe_id: int
