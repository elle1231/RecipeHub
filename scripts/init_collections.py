"""Qdrant 双知识库 Collection 初始化脚本（RH-17）。

职责：连接本地 Qdrant，幂等创建 public_recipes / personal_kitchens
两个 Collection，并按 settings.embedding_dim 定死向量维度。

用法（从仓库根目录执行）：
    python scripts/init_collections.py

幂等：Collection 已存在则跳过（重复运行不会丢数据或报错）。
等价于 FastAPI 启动时 lifespan 里的 ensure_collections()，单独跑便于
在写向量（RH-19）之前手动确认 Collection 已就绪。
"""
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"

os.chdir(BACKEND_DIR)  # 让 config 的 env_file=".env" 正确解析
sys.path.insert(0, str(BACKEND_DIR))

from app.db.qdrant import get_qdrant_client  # noqa: E402
from app.services.rag.collections import ensure_collections  # noqa: E402
from app.services.rag.schemas import PERSONAL_COLLECTION, PUBLIC_COLLECTION  # noqa: E402


def main() -> None:
    client = get_qdrant_client()
    created = ensure_collections(client)

    for name, was_created in created.items():
        action = "新建" if was_created else "已存在（跳过）"
        print(f"[{name}] {action}")

    # 二次确认，防止「创建成功但集合为空」这类误判被掩盖。
    print(f"当前 Qdrant Collection 数量：{len(client.get_collections().collections)}")
    print(f"  公共知识库 {PUBLIC_COLLECTION}：存在={client.collection_exists(PUBLIC_COLLECTION)}")
    print(f"  个人知识库 {PERSONAL_COLLECTION}：存在={client.collection_exists(PERSONAL_COLLECTION)}")


if __name__ == "__main__":
    main()
