"""公共菜谱数据导入的解析逻辑（RH-10）。

从上游 HowToCook 风格的 Markdown 菜谱文件中提取
title / description / difficulty / ingredients / steps。

本模块只做「纯解析」（md 文本 → 结构化 dict），便于单测；
读写文件系统、JSON 索引和数据库的编排放在 scripts/import_public_recipes.py。
"""
from __future__ import annotations

import re

# 「预估烹饪难度」的 ★ 数量 → 难度标签（1-2 简单 / 3 中等 / 4 困难）
_STAR_TO_DIFFICULTY = {1: "简单", 2: "简单", 3: "中等", 4: "困难"}
_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")


def parse_dish_markdown(text: str) -> dict:
    """解析一篇菜谱 Markdown，返回结构化字段。

    返回 dict：{
        title, description, difficulty,          # 字符串或 None
        ingredients: [{"ingredient_name", "quantity"}],
        steps: [str],
    }
    """
    lines = text.splitlines()

    title = _extract_title(lines)
    difficulty = _extract_difficulty(lines)
    description = _extract_description(lines)

    ingredient_names: list[str] = []  # 「必备原料和工具」段（无用量）
    ingredient_calc: list[str] = []   # 「计算」段（含用量）
    steps: list[str] = []

    current_section: str | None = None
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            current_section = stripped[3:].strip()
            continue
        item = _strip_bullet(stripped)
        if item is None:
            continue

        if current_section == "必备原料和工具":
            ingredient_names.append(item)
        elif current_section == "计算":
            ingredient_calc.append(item)
        elif current_section == "操作":
            steps.append(item)

    # 食材优先用「计算」段（含用量），没有则退化为「必备原料」段（只有名称）
    if ingredient_calc:
        ingredients = _parse_calc_ingredients(ingredient_calc)
    else:
        ingredients = [{"ingredient_name": name, "quantity": None} for name in ingredient_names]

    return {
        "title": title,
        "description": description,
        "difficulty": difficulty,
        "ingredients": ingredients,
        "steps": steps,
    }


def _strip_bullet(stripped: str) -> str | None:
    """识别 Markdown 列表项（无序 `- ` / `* ` / `+ `，或有序 `1. ` / `1、` / `1) `），返回内容；否则 None。"""
    m = re.match(r"^(?:[-*+]\s+|\d+[.、)]\s*)(.*)$", stripped)
    if m:
        return m.group(1).strip()
    return None


def _extract_title(lines: list[str]) -> str | None:
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("# ") and "的做法" in stripped:
            return stripped[2:].replace("的做法", "").strip()
    return None


def _extract_difficulty(lines: list[str]) -> str | None:
    for line in lines:
        m = re.search(r"预估烹饪难度[：:]\s*([★☆]+)", line)
        if m:
            return _STAR_TO_DIFFICULTY.get(m.group(1).count("★"))
    return None


def _extract_description(lines: list[str]) -> str | None:
    """标题之后、第一个 `## ` 之前的非空段落（排除难度行和图片行）。"""
    parts: list[str] = []
    started = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            break
        if stripped.startswith("# ") and "的做法" in stripped:
            started = True
            continue
        if not started:
            continue
        if not stripped or stripped.startswith("预估烹饪难度"):
            continue
        # 跳过 HTML 注释、引用块
        if stripped.startswith("<!--") or stripped.startswith(">"):
            continue
        # 去掉行内图片引用（`![...](...)`），纯图片行整体跳过
        stripped = _IMAGE_RE.sub("", stripped).strip()
        if stripped:
            parts.append(stripped)
    return "\n".join(parts).strip() or None


def _parse_calc_ingredients(items: list[str]) -> list[dict]:
    """解析「计算」段的食材行，拆成 {"ingredient_name", "quantity"}。

    兼容两种写法：
    - 空格分隔： "肉蟹 1 只（大约 300g） * 份数" → 肉蟹 / 1 只（大约 300g）
    - 冒号分隔： "干木耳: 20g / 湿木耳: 120g"         → 干木耳 / 20g / 湿木耳: 120g
    """
    result: list[dict] = []
    for item in items:
        m = re.match(r"^([^\s\d:：]+)[:：]?\s*(.*)$", item)
        if not m:
            continue
        name = m.group(1).strip()
        quantity = m.group(2).strip() or None
        if quantity:
            quantity = quantity.replace("* 份数", "").replace("*份数", "").strip() or None
        if name:
            result.append({"ingredient_name": name, "quantity": quantity})
    return result
