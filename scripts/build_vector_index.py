"""向量索引构建脚本（RH-19）。

职责：读 SQLite → Chunking → Embedding → Qdrant Upsert。
公共菜谱进 public_recipes，个人菜谱 + 制作记录进 personal_kitchens。

用法（从仓库根目录执行）：
    python scripts/build_vector_index.py                    # 增量构建（同 document_id 覆盖）
    python scripts/build_vector_index.py --reset            # 先清空两个 Collection 再全量重建
    python scripts/build_vector_index.py --skip-personal    # 只构建公共知识库
    python scripts/build_vector_index.py --dry-run          # 只统计切分结果，不写向量

幂等：point id 由 document_id 确定性生成，重复运行覆盖而非新增。
"""
import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"

os.chdir(BACKEND_DIR)
sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import settings  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402
from app.db.qdrant import get_qdrant_client  # noqa: E402
from app.services.rag.embedding import get_embedding_service  # noqa: E402
from app.services.rag.index import (  # noqa: E402
    build_index,
    collect_personal_chunks,
    collect_public_chunks,
)
from app.services.rag.schemas import PERSONAL_COLLECTION, PUBLIC_COLLECTION  # noqa: E402


def _reset_collections(client) -> None:
    """清空两个 Collection（下次 ensure_collections 会重建，含索引）。"""
    for name in (PUBLIC_COLLECTION, PERSONAL_COLLECTION):
        if client.collection_exists(name):
            client.delete_collection(name)
    print("已清空 Collection，将全量重建")


def main() -> None:
    parser = argparse.ArgumentParser(description="构建 RecipeHub 向量索引")
    parser.add_argument("--reset", action="store_true", help="先清空 Collection 再全量重建")
    parser.add_argument("--skip-personal", action="store_true", help="跳过个人知识库")
    parser.add_argument("--dry-run", action="store_true", help="只统计切分结果，不写向量")
    args = parser.parse_args()

    init_db()
    db = SessionLocal()
    client = get_qdrant_client()
    try:
        if args.dry_run:
            pub = collect_public_chunks(db)
            per = collect_personal_chunks(db) if not args.skip_personal else []
            print(f"[dry-run] 公共菜谱 Chunk：{len(pub)}")
            print(f"[dry-run] 个人知识 Chunk：{len(per)}")
            return

        if args.reset:
            _reset_collections(client)

        embedder = get_embedding_service()
        print(f"使用 embedding：model={settings.embedding_model}，"
              f"维度={embedder.dimension}，后端={type(embedder).__name__}")

        stats = build_index(db, client, embedder, include_personal=not args.skip_personal)
        print(f"embedding：{stats['embedding']}")
        print(f"{PUBLIC_COLLECTION}：chunk {stats[PUBLIC_COLLECTION]['chunks']} → 写入 {stats[PUBLIC_COLLECTION]['points']} 点")
        print(f"{PERSONAL_COLLECTION}：chunk {stats[PERSONAL_COLLECTION]['chunks']} → 写入 {stats[PERSONAL_COLLECTION]['points']} 点")
    finally:
        db.close()


if __name__ == "__main__":
    main()
