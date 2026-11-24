"""SQLAlchemy 声明式基类与通用时间工具。

所有 ORM 模型都继承这里的 `Base`，这样 `Base.metadata.create_all()`
能一次性建出全部表（前提是模型文件都被 import 过，见 models/__init__.py）。
"""
from datetime import datetime, timezone

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """所有 ORM 模型的公共基类。"""


def utcnow() -> datetime:
    """返回「无时区的 UTC 时间」。

    SQLite 的 DateTime 不存时区，用 naive UTC 最稳妥；
    存进去统一是 UTC，展示时再转本地时区。
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)
