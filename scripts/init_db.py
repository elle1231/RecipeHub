"""手动建表脚本（从仓库根目录执行）：

    python scripts/init_db.py

会自动切到 backend/ 目录并把 backend 加入 sys.path，
这样 `app` 包和 `backend/.env` 都能正确解析。
（应用启动时 lifespan 也会自动建表，此脚本用于不启动服务时手动初始化。）
"""
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
os.chdir(BACKEND_DIR)  # 让 config 里 env_file=".env" 的相对路径正确解析
sys.path.insert(0, str(BACKEND_DIR))

from app.db import init_db  # noqa: E402

if __name__ == "__main__":
    init_db()
    print("数据库建表完成。")
