"""用户相关服务。

本地演示阶段用 openid 标识用户；openid → users.id 的映射在这里完成。
采用「首次请求即建用户」（get_or_create），省去手动初始化测试用户的步骤。
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User


def get_or_create_user(db: Session, openid: str) -> User:
    """按 openid 取用户；不存在则创建并返回已持久化的 User。

    这是 deps.get_current_user_id（返回 openid）到 users.id 的桥接点：
    recipes.owner_id 等外键指向 users.id（整数），而请求头里只有 openid（字符串）。
    """
    user = db.scalar(select(User).where(User.openid == openid))
    if user is None:
        user = User(openid=openid, nickname=openid)
        db.add(user)
        db.commit()
        db.refresh(user)
    return user
