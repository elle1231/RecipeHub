"""RAG 数据切分策略（RH-18）。

把一个菜谱 / 制作记录切成适合向量化的 Chunk。核心原则（PLAN Day3 任务3）：

1. 一道菜谱的「标题 + 描述 + 食材 + 步骤」是完整语义单元，短菜谱整体一个 Chunk；
2. 长菜谱拆分时，首块保留「标题 + 描述 + 食材」作概览，步骤按顺序切块，
   每块前缀标题——既保住步骤顺序，又不产生失去上下文的碎片；
3. 绝不把多道菜混进一个 Chunk（一次调用只切一道菜 / 一条记录）。

纯函数、无 IO，方便单测；ORM → 字符串的转换由 format_ingredient /
format_step 完成，RH-19 的 build_vector_index.py 负责「读库 → 组装 → 调这里」。
"""
from __future__ import annotations

from app.services.rag.schemas import (
    DocumentType,
    PersonalKitchenChunk,
    PublicRecipeChunk,
)

__all__ = [
    "MAX_CHUNK_CHARS",
    "format_ingredient",
    "format_step",
    "chunk_recipe_text",
    "build_public_chunks",
    "build_personal_recipe_chunks",
    "build_cooking_note_chunks",
]

# 单 Chunk 硬上限（字符数）。BGE-small-zh-v1.5 最大 512 token，
# 中文大致 1 字 ≈ 1~2 token，取 800 字偏保守，宁可多切一点也不截断语义。
MAX_CHUNK_CHARS = 800


# ---------- 结构化字段 → 文本 ----------

def format_ingredient(ingredient) -> str:
    """把一条食材（ORM RecipeIngredient 或等价对象）格式化成文本。

    「番茄 2个」/「盐 适量」/「香菜（可选，点缀）」。
    quantity/unit 用「空格 + 用量 + 单位」拼接，缺失则省略。
    """
    name = getattr(ingredient, "ingredient_name", "")
    quantity = getattr(ingredient, "quantity", None)
    unit = getattr(ingredient, "unit", None)
    note = getattr(ingredient, "optional_note", None)

    # 数量与单位直接相连（「2个」「500克」），中间不留空格，更符合中文书写习惯。
    amount = f"{quantity or ''}{unit or ''}".strip()
    text = name if not amount else f"{name} {amount}"
    if note:
        text = f"{text}（{note}）"
    return text


def format_step(step) -> str:
    """把一条步骤（ORM RecipeStep 或等价对象）格式化成文本。

    「热锅倒油」/「大火翻炒 3 分钟」。heat_level / duration_minutes 缺失则省略。
    """
    instruction = getattr(step, "instruction", "")
    heat = getattr(step, "heat_level", None)
    duration = getattr(step, "duration_minutes", None)

    if heat and duration:
        return f"{instruction}（{heat}，约 {duration} 分钟）"
    if heat:
        return f"{instruction}（{heat}）"
    if duration:
        return f"{instruction}（约 {duration} 分钟）"
    return instruction


# ---------- 核心切分 ----------

def _format_overview(title: str, description: str | None, ingredients: list[str]) -> str:
    parts = [f"【{title}】"]
    if description:
        parts.append(f"描述：{description}")
    if ingredients:
        parts.append("食材：" + "、".join(ingredients))
    return "\n".join(parts)


def chunk_recipe_text(
    title: str,
    description: str | None,
    ingredients: list[str],
    steps: list[str],
    max_chars: int = MAX_CHUNK_CHARS,
) -> list[str]:
    """把一道菜谱的正文切成若干 chunk 文本（不含 metadata，便于单测）。

    规则：
    - 整体 ≤ max_chars 或没有步骤 → 一个 chunk（完整正文）。
    - 超长 → 首块 = 概览（标题+描述+食材），步骤按顺序打包，
      每块以标题开头，保证步骤顺序与菜谱关联不丢。
    """
    overview = _format_overview(title, description, ingredients)
    step_lines = [f"{i + 1}. {s}" for i, s in enumerate(steps)]

    if not step_lines:
        return [overview]

    full = overview + "\n\n" + f"【{title}】\n步骤：\n" + "\n".join(step_lines)
    if len(full) <= max_chars:
        return [full]

    # 概览单独成块（避免步骤切块后丢掉「这是哪道菜、需要什么」）。
    chunks: list[str] = []
    if overview.strip():
        chunks.append(overview)

    # 步骤按顺序打包，超限就开新块；每块都带标题前缀，避免碎片失去上下文。
    header = f"【{title}】\n步骤："
    current_lines = [header]
    current_len = len(header)
    for line in step_lines:
        added = len(line) + 1  # 换行符
        if current_len + added > max_chars and len(current_lines) > 1:
            chunks.append("\n".join(current_lines))
            current_lines = [header, line]
            current_len = len(header) + len(line) + 1
        else:
            current_lines.append(line)
            current_len += added
    if len(current_lines) > 1:
        chunks.append("\n".join(current_lines))

    return chunks


# ---------- 组装成带 metadata 的 Chunk ----------

def build_public_chunks(
    *,
    recipe_id: int,
    title: str,
    description: str | None,
    ingredients: list[str],
    steps: list[str],
    source: str | None,
    category: str | None,
) -> list[PublicRecipeChunk]:
    """把公共菜谱切成 PublicRecipeChunk 列表。

    document_id = public_recipe_{recipe_id}#{i}，i 为 0 起始的块序号，
    保证重复索引时幂等覆盖而不是新增（RH-19 直接复用）。
    """
    texts = chunk_recipe_text(title, description, ingredients, steps)
    total = len(texts)
    return [
        PublicRecipeChunk(
            document_id=f"public_recipe_{recipe_id}#{i}",
            recipe_id=recipe_id,
            title=title,
            content=text,
            source=source,
            category=category,
            document_type=DocumentType.RECIPE,
            chunk_index=i,
            total_chunks=total,
        )
        for i, text in enumerate(texts)
    ]


def build_personal_recipe_chunks(
    *,
    user_id: int,
    recipe_id: int,
    title: str,
    description: str | None,
    ingredients: list[str],
    steps: list[str],
    version: int = 1,
    verified: bool = False,
    visibility: str = "private",
) -> list[PersonalKitchenChunk]:
    """把个人菜谱切成 PersonalKitchenChunk 列表，user_id 用内部整数。"""
    texts = chunk_recipe_text(title, description, ingredients, steps)
    total = len(texts)
    return [
        PersonalKitchenChunk(
            document_id=f"personal_recipe_{user_id}_{recipe_id}#{i}",
            user_id=user_id,
            recipe_id=recipe_id,
            title=title,
            content=text,
            version=version,
            verified=verified,
            visibility=visibility,
            document_type=DocumentType.PERSONAL_RECIPE,
            chunk_index=i,
            total_chunks=total,
        )
        for i, text in enumerate(texts)
    ]


def build_cooking_note_chunks(
    *,
    user_id: int,
    record_id: int,
    recipe_id: int | None,
    title: str,
    content: str,
) -> list[PersonalKitchenChunk]:
    """把一条制作记录/经验切成 Chunk（默认整条一个，超长按段落粗切）。

    制作记录通常较短（问题、下次调整），一条一个 Chunk 即可；
    超长时按换行段落累积到 MAX_CHUNK_CHARS 切块。
    """
    chunks: list[str] = []
    if len(content) <= MAX_CHUNK_CHARS:
        chunks = [content]
    else:
        current: list[str] = []
        current_len = 0
        for para in content.split("\n"):
            added = len(para) + 1
            if current_len + added > MAX_CHUNK_CHARS and current:
                chunks.append("\n".join(current))
                current, current_len = [para], added
            else:
                current.append(para)
                current_len += added
        if current:
            chunks.append("\n".join(current))

    total = len(chunks)
    return [
        PersonalKitchenChunk(
            document_id=f"cooking_note_{user_id}_{record_id}#{i}",
            user_id=user_id,
            recipe_id=recipe_id,
            title=title,
            content=text,
            version=1,
            verified=True,
            visibility="private",
            document_type=DocumentType.COOKING_NOTE,
            chunk_index=i,
            total_chunks=total,
        )
        for i, text in enumerate(chunks)
    ]
