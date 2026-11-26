"""RAG 切分预览脚本（RH-18）。

职责：读 SQLite 里的公共菜谱，跑一遍 chunking，输出切分统计与样例，
用于在「真正向量化（RH-19）」之前人工检查切分质量（是否过度切碎 / 步骤是否乱序）。

用法（从仓库根目录执行）：
    python scripts/preview_chunking.py              # 预览全部公共菜谱的切分统计
    python scripts/preview_chunking.py --limit 10   # 只看前 10 条
    python scripts/preview_chunking.py --sample 3   # 额外打印 3 条切分样例全文
"""
import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"

os.chdir(BACKEND_DIR)
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal, init_db  # noqa: E402
from app.models import Recipe  # noqa: E402
from app.services.rag.chunking import (  # noqa: E402
    build_public_chunks,
    format_ingredient,
    format_step,
)


def _preview_one(recipe: Recipe) -> list:
    return build_public_chunks(
        recipe_id=recipe.id,
        title=recipe.title,
        description=recipe.description,
        ingredients=[format_ingredient(i) for i in recipe.ingredients],
        steps=[format_step(s) for s in recipe.steps],
        source=recipe.source,
        category=recipe.category,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="预览公共菜谱切分结果")
    parser.add_argument("--limit", type=int, default=None, help="最多预览条数")
    parser.add_argument("--sample", type=int, default=0, help="额外打印前 N 条切分样例全文")
    args = parser.parse_args()

    init_db()
    db = SessionLocal()
    try:
        stmt = (
            select(Recipe)
            .where(Recipe.owner_id.is_(None))
            .order_by(Recipe.id)
        )
        if args.limit:
            stmt = stmt.limit(args.limit)
        recipes = list(db.scalars(stmt).all())

        if not recipes:
            print("没有公共菜谱，先跑 scripts/import_public_recipes.py")
            return

        all_chunks = []
        for r in recipes:
            all_chunks.extend(_preview_one(r))

        sizes = [len(c.content) for c in all_chunks]
        multi = sum(1 for r in recipes if len(_preview_one(r)) > 1)

        print(f"菜谱数：{len(recipes)}，切出 Chunk 数：{len(all_chunks)}")
        print(f"平均 Chunk/菜谱：{len(all_chunks) / len(recipes):.2f}")
        print(f"被切成多块的菜谱：{multi} 条")
        print(f"Chunk 字符数：min={min(sizes)}，max={max(sizes)}，avg={sum(sizes) / len(sizes):.0f}")
        print(f"超过 800 字上限的 Chunk：{sum(1 for s in sizes if s > 800)} 个")

        for r in recipes[: args.sample]:
            chunks = _preview_one(r)
            print(f"\n===== 菜谱 #{r.id}《{r.title}》→ {len(chunks)} 块 =====")
            for c in chunks:
                print(f"--- {c.document_id}（{len(c.content)} 字）---")
                print(c.content)
    finally:
        db.close()


if __name__ == "__main__":
    main()
