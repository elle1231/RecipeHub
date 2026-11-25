"""公共菜谱数据导入脚本（RH-10）。

数据源：上游 What-to-eat-today 仓库的 data/recipes_with_images.json（索引）
        + data/dishes/**/*.md（菜谱全文，含食材/步骤）。
职责：清洗、去重、统一字段后写入 SQLite 的 recipes 表（owner_id 为 NULL = 公共菜谱）。

用法（从仓库根目录执行）：
    python scripts/import_public_recipes.py                # 默认导入 ../what-to-eat-upstream
    python scripts/import_public_recipes.py --upstream D:/path/to/upstream
    python scripts/import_public_recipes.py --limit 50     # 只导前 50 条
    python scripts/import_public_recipes.py --reset        # 先清空公共菜谱再导入

幂等：按 recipes.source 去重，已存在则跳过，重复运行不会重复导入。
"""
import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
DEFAULT_UPSTREAM = REPO_ROOT.parent / "what-to-eat-upstream"

os.chdir(BACKEND_DIR)  # 让 config 的 env_file=".env" 与 DB 相对路径正确解析
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import func, select  # noqa: E402

from app.db import SessionLocal, init_db  # noqa: E402
from app.models import Recipe, RecipeIngredient, RecipeStep  # noqa: E402
from app.services.recipe.public_import import parse_dish_markdown  # noqa: E402

_DIFFICULTY_ONLY = "预估烹饪难度"  # JSON description 里混入的噪声前缀


def _clean_json_description(desc: str | None) -> str | None:
    """清洗 JSON 里的 description：若只是「预估烹饪难度：★★」这类噪声则视为空。"""
    if not desc:
        return None
    stripped = desc.strip()
    if stripped.startswith(_DIFFICULTY_ONLY):
        return None
    return stripped


def _load_index(upstream: Path) -> list[dict]:
    index_path = upstream / "data" / "recipes_with_images.json"
    if not index_path.exists():
        raise FileNotFoundError(f"未找到菜谱索引：{index_path}")
    return json.loads(index_path.read_text(encoding="utf-8"))


def _reset_public_recipes(db) -> None:
    """清空所有公共菜谱（owner_id 为 NULL），用于 --reset 全量重导。

    用 ORM 级 delete（而非 bulk delete）触发 recipe_ingredients / recipe_steps
    的 cascade 删除，避免留下孤儿食材/步骤行。
    """
    recipes = db.scalars(select(Recipe).where(Recipe.owner_id.is_(None))).all()
    for recipe in recipes:
        db.delete(recipe)
    db.commit()


def _build_recipe(entry: dict, parsed: dict, source: str) -> Recipe:
    """把一条索引 + 解析结果组装成 Recipe（不含食材/步骤，那些单独建）。"""
    description = parsed["description"] or _clean_json_description(entry.get("description"))
    cooking_time = entry.get("cooking_time") or None
    return Recipe(
        owner_id=None,
        source=source,
        title=parsed["title"] or entry.get("name", ""),
        description=description,
        image_url=entry.get("image_url"),
        category=entry.get("category"),
        cuisine=None,  # 上游数据无菜系字段，不编造
        cooking_time=cooking_time,
        difficulty=parsed["difficulty"],
        status="Draft",
        visibility="public",
        orderable=False,
        current_version=1,
    )


def _import_one(db, upstream: Path, entry: dict) -> str:
    """导入单条；返回 'ok' / 'skip' / 'missing' / 'fail'。"""
    raw_path = entry.get("file_path", "")
    rel_path = raw_path.replace("\\", "/")
    source = rel_path
    md_path = upstream / rel_path

    if not md_path.exists():
        return "missing"

    # 幂等：同一来源已导入则跳过
    exists = db.scalar(select(Recipe).where(Recipe.source == source))
    if exists is not None:
        return "skip"

    try:
        md_text = md_path.read_text(encoding="utf-8")
    except Exception:
        return "fail"

    parsed = parse_dish_markdown(md_text)
    recipe = _build_recipe(entry, parsed, source)
    recipe.ingredients = [
        RecipeIngredient(sort_order=i, **ing)
        for i, ing in enumerate(parsed["ingredients"])
    ]
    recipe.steps = [
        RecipeStep(step_number=i + 1, instruction=step)
        for i, step in enumerate(parsed["steps"])
    ]
    db.add(recipe)
    db.commit()
    return "ok"


def main() -> None:
    parser = argparse.ArgumentParser(description="导入公共菜谱数据到 SQLite")
    parser.add_argument("--upstream", type=Path, default=DEFAULT_UPSTREAM, help="上游仓库路径")
    parser.add_argument("--limit", type=int, default=None, help="最多导入条数（调试用）")
    parser.add_argument("--reset", action="store_true", help="先清空公共菜谱再导入")
    args = parser.parse_args()

    init_db()  # 确保表存在（含新增的 source 列）

    db = SessionLocal()
    try:
        if args.reset:
            _reset_public_recipes(db)

        entries = _load_index(args.upstream)
        if args.limit:
            entries = entries[: args.limit]

        stats = {"ok": 0, "skip": 0, "missing": 0, "fail": 0}
        for entry in entries:
            outcome = _import_one(db, args.upstream, entry)
            stats[outcome] += 1

        count = db.scalar(
            select(func.count()).select_from(Recipe).where(Recipe.owner_id.is_(None))
        )
        print(f"索引共 {len(entries)} 条：新增 {stats['ok']}，跳过(已存在) {stats['skip']}，"
              f"文件缺失 {stats['missing']}，解析失败 {stats['fail']}")
        print(f"当前公共菜谱总数：{count}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
