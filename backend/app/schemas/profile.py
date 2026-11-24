"""用户饮食画像 Schema。"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class UserProfileBase(BaseModel):
    dietary_goal: str | None = None
    taste_preferences: list[str] | None = None
    disliked_ingredients: list[str] | None = None
    allergens: list[str] | None = None
    dietary_habits: list[str] | None = None
    max_cooking_time: int | None = None


class UserProfileUpdate(UserProfileBase):
    """更新画像请求。全字段可选，未传的保持原值。"""


class UserProfileRead(UserProfileBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    updated_at: datetime
