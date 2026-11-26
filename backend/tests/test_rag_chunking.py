"""RH-18 数据切分策略的单元测试。

纯函数无 IO，不依赖数据库 / Qdrant。重点验证：
- 短菜谱整体一个 Chunk，长菜谱按「概览 + 有序步骤」切块；
- 步骤顺序不丢、每块带标题前缀、不产生失去上下文的碎片；
- metadata（recipe_id / user_id / version / visibility 等）完整保留。
"""
from types import SimpleNamespace

from app.services.rag.chunking import (
    MAX_CHUNK_CHARS,
    build_cooking_note_chunks,
    build_personal_recipe_chunks,
    build_public_chunks,
    chunk_recipe_text,
    format_ingredient,
    format_step,
)
from app.services.rag.schemas import DocumentType


# ---------- 结构化字段格式化 ----------

def test_format_ingredient_full():
    ing = SimpleNamespace(ingredient_name="番茄", quantity="2", unit="个", optional_note="切块")
    assert format_ingredient(ing) == "番茄 2个（切块）"


def test_format_ingredient_quantity_only():
    ing = SimpleNamespace(ingredient_name="盐", quantity="适量", unit=None, optional_note=None)
    assert format_ingredient(ing) == "盐 适量"


def test_format_step_with_heat_and_duration():
    step = SimpleNamespace(instruction="翻炒", heat_level="大火", duration_minutes=3)
    assert format_step(step) == "翻炒（大火，约 3 分钟）"


def test_format_step_bare():
    step = SimpleNamespace(instruction="出锅", heat_level=None, duration_minutes=None)
    assert format_step(step) == "出锅"


# ---------- 核心切分 ----------

def test_short_recipe_is_one_chunk():
    texts = chunk_recipe_text(
        title="番茄炒蛋",
        description="家常快手菜",
        ingredients=["番茄 2个", "鸡蛋 3个", "盐 适量"],
        steps=["鸡蛋打散", "番茄切块", "先炒蛋再下番茄", "调味出锅"],
    )
    assert len(texts) == 1
    text = texts[0]
    assert "番茄炒蛋" in text and "番茄 2个" in text and "调味出锅" in text


def test_no_steps_returns_single_overview_chunk():
    texts = chunk_recipe_text(
        title="清蒸鱼", description=None, ingredients=["鲈鱼 1条"], steps=[]
    )
    assert len(texts) == 1
    assert "鲈鱼 1条" in texts[0]


def test_long_recipe_splits_overview_then_ordered_steps():
    steps = [f"第{i}步：把食材{i}放进锅里，用中火慢慢加热，直到香气出来。" for i in range(1, 31)]
    texts = chunk_recipe_text(
        title="超长菜谱",
        description="用来测试切块",
        ingredients=["食材A", "食材B"],
        steps=steps,
    )
    assert len(texts) >= 2
    # 首块是概览：含标题与食材
    assert "超长菜谱" in texts[0] and "食材A" in texts[0]
    # 后续块都带标题前缀，避免碎片失去上下文
    assert all(t.startswith("【超长菜谱】\n步骤：") for t in texts[1:])
    # 步骤顺序完整保留：把后续块的步骤拼接起来，按原顺序出现
    joined = "".join(texts[1:])
    for i, s in enumerate(steps, start=1):
        assert f"{i}. {s}" in joined
    # 每块不超硬上限
    assert all(len(t) <= MAX_CHUNK_CHARS for t in texts)


def test_never_mixes_other_recipe():
    # 单次调用只切一道菜，天然不会混入别的菜；这里只验证切块内容只含本题。
    texts = chunk_recipe_text(
        title="红烧肉", description=None, ingredients=["五花肉"], steps=["焯水", "炒糖色"]
    )
    assert len(texts) == 1
    assert "番茄" not in texts[0]


# ---------- 组装 Chunk ----------

def test_build_public_chunks_preserves_metadata():
    chunks = build_public_chunks(
        recipe_id=42,
        title="番茄炒蛋",
        description="家常",
        ingredients=["番茄", "鸡蛋"],
        steps=["炒"],
        source="howtocook/tomato.md",
        category="家常菜",
    )
    assert len(chunks) == 1
    c = chunks[0]
    assert c.document_id == "public_recipe_42#0"
    assert c.recipe_id == 42
    assert c.source == "howtocook/tomato.md"
    assert c.category == "家常菜"
    assert c.document_type == DocumentType.RECIPE
    assert c.chunk_index == 0 and c.total_chunks == 1


def test_build_personal_recipe_chunks_preserves_metadata():
    chunks = build_personal_recipe_chunks(
        user_id=7,
        recipe_id=101,
        title="我的番茄炒蛋",
        description=None,
        ingredients=["番茄", "鸡蛋"],
        steps=["少放糖"],
        version=2,
        verified=True,
        visibility="private",
    )
    assert len(chunks) == 1
    c = chunks[0]
    assert c.document_id == "personal_recipe_7_101#0"
    assert c.user_id == 7 and c.recipe_id == 101
    assert c.version == 2 and c.verified is True and c.visibility == "private"
    assert c.document_type == DocumentType.PERSONAL_RECIPE


def test_build_cooking_note_chunks_marks_verified():
    chunks = build_cooking_note_chunks(
        user_id=7,
        record_id=9,
        recipe_id=101,
        title="番茄炒蛋",
        content="上次太咸，这次少放盐。",
    )
    assert len(chunks) == 1
    c = chunks[0]
    assert c.document_id == "cooking_note_7_9#0"
    assert c.document_type == DocumentType.COOKING_NOTE
    assert c.verified is True and c.visibility == "private"
    assert c.user_id == 7 and c.recipe_id == 101


def test_long_public_recipe_gets_multiple_chunks_with_indexes():
    steps = [f"第{i}步：处理食材{i}并放入锅中翻炒均匀。" for i in range(1, 40)]
    chunks = build_public_chunks(
        recipe_id=1,
        title="长菜谱",
        description=None,
        ingredients=["食材"],
        steps=steps,
        source=None,
        category=None,
    )
    assert len(chunks) >= 2
    # chunk_index 从 0 连续递增，total_chunks 一致
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
    assert all(c.total_chunks == len(chunks) for c in chunks)
    # document_id 唯一
    ids = [c.document_id for c in chunks]
    assert len(ids) == len(set(ids))
