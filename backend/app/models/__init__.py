"""ORM 模型统一入口。

这里必须 import 所有模型，`Base.metadata.create_all()` 才能
把每张表都注册进去。新增模型文件后记得在这里加一行 import。
"""
from app.models.menu import Menu, MenuRecipeDraft
from app.models.recipe import CookingRecord, Recipe, RecipeIngredient, RecipeStep, RecipeVersion
from app.models.user import User, UserProfile

__all__ = [
    "User",
    "UserProfile",
    "Recipe",
    "RecipeIngredient",
    "RecipeStep",
    "RecipeVersion",
    "CookingRecord",
    "Menu",
    "MenuRecipeDraft",
]
