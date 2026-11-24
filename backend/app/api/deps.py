"""API 通用依赖。"""
from fastapi import Header


def get_current_user_id(x_user_id: str = Header(default="demo_user", alias="X-User-Id")) -> str:
    """本地演示阶段：从请求头 X-User-Id 取用户标识，默认 demo_user。

    正式接入微信登录后，这里会替换为「解析后端签发的 token → 用户」。
    返回值是 users.openid；映射到 users.id 由 service 层完成。
    """
    return x_user_id
