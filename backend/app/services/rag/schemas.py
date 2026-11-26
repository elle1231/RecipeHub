"""RAG 文档结构定义（RH-17）。

这里只定义「向量库里一个 Chunk 长什么样」——即 Qdrant 的 Payload
（元数据）和待向量化的正文文本。菜谱名称、食材用量、步骤等精确字段
仍以 SQLite 为准；向量库只放适合语义检索的文本 + 溯源元数据。

两个 Collection 的 Payload 字段不同，因此拆成两个 Pydantic 模型：
- PublicRecipeChunk    —— 公共菜谱知识库 `public_recipes`
- PersonalKitchenChunk —— 个人厨房知识库 `personal_kitchens`

注意 user_id 用「内部整数 users.id」而非 openid 字符串，与 SQL 里
recipes.owner_id 保持一致，RH-20 检索按它过滤个人知识。
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

# Collection 名称在这里定死，RH-17/19/20 共用，避免散落魔法字符串。
PUBLIC_COLLECTION = "public_recipes"
PERSONAL_COLLECTION = "personal_kitchens"


class DocumentType(str, Enum):
    """Chunk 的内容类型，用于检索时区分「菜谱正文 / 烹饪技巧 / 个人经验」。"""

    # 公共知识库
    RECIPE = "recipe"                       # 菜谱正文（描述 + 食材 + 步骤）
    INGREDIENT_KNOWLEDGE = "ingredient_knowledge"  # 食材知识（替换、挑选等）
    COOKING_SKILL = "cooking_skill"         # 通用烹饪技巧
    # 个人知识库
    PERSONAL_RECIPE = "personal_recipe"     # 用户自己的菜谱
    COOKING_NOTE = "cooking_note"           # 制作记录 / 烹饪笔记
    EXPERIENCE = "experience"               # 菜谱调整经验


class PublicRecipeChunk(BaseModel):
    """公共菜谱知识库的一个 Chunk。

    document_id 是全局唯一的主键，由「来源 + 菜谱 + 分片序号」拼出，
    保证重复索引时幂等覆盖而不是重复插入。
    """

    document_id: str
    recipe_id: int
    title: str
    content: str = Field(description="待向量化的正文：描述 + 食材 + 步骤 + 技巧")
    source: str | None = Field(default=None, description="数据出处（文件路径/来源名），版权溯源")
    category: str | None = None
    document_type: DocumentType = DocumentType.RECIPE


class PersonalKitchenChunk(BaseModel):
    """个人厨房知识库的一个 Chunk。

    user_id 是内部 users.id（整数），不是 openid。visibility / verified
    直接从 SQL 同步过来，但只是辅助——真正的权限判定永远以 SQL 为准。
    """

    document_id: str
    user_id: int = Field(description="内部 users.id，与 recipes.owner_id 一致")
    recipe_id: int | None = Field(default=None, description="关联的菜谱 id，纯经验笔记可为空")
    title: str
    content: str = Field(description="待向量化的正文：菜谱 / 制作记录 / 调整经验")
    version: int = 1
    verified: bool = False
    visibility: str = "private"
    document_type: DocumentType = DocumentType.PERSONAL_RECIPE
