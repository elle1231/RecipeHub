"""RH-10 菜谱 Markdown 解析逻辑的单元测试。"""
from app.services.recipe.public_import import parse_dish_markdown

SAMPLE = """# 咖喱炒蟹的做法

第一次吃咖喱炒蟹是在泰国的建兴酒家中餐厅。

预估烹饪难度：★★★★

## 必备原料和工具

- 青蟹（别称：肉蟹）
- 咖喱块
- 洋葱

## 计算

每次制作前需要确定计划做几份。一份正好够 1 个人食用

总量：

- 肉蟹 1 只（大约 300g） * 份数
- 咖喱块 15g（一小块）*份数
- 洋葱 200g *份数

## 操作

- 肉蟹掀盖后对半砍开
- 洋葱切成洋葱碎
"""


def test_parse_title_strips_suffix():
    assert parse_dish_markdown(SAMPLE)["title"] == "咖喱炒蟹"


def test_parse_difficulty_maps_stars():
    assert parse_dish_markdown(SAMPLE)["difficulty"] == "困难"


def test_parse_description_excludes_difficulty_line():
    assert parse_dish_markdown(SAMPLE)["description"] == "第一次吃咖喱炒蟹是在泰国的建兴酒家中餐厅。"


def test_parse_ingredients_from_calc_with_quantity():
    ings = parse_dish_markdown(SAMPLE)["ingredients"]
    assert ings == [
        {"ingredient_name": "肉蟹", "quantity": "1 只（大约 300g）"},
        {"ingredient_name": "咖喱块", "quantity": "15g（一小块）"},
        {"ingredient_name": "洋葱", "quantity": "200g"},
    ]


def test_parse_steps_in_order():
    assert parse_dish_markdown(SAMPLE)["steps"] == [
        "肉蟹掀盖后对半砍开",
        "洋葱切成洋葱碎",
    ]


def test_parse_falls_back_to_ingredient_names_when_no_calc():
    md = """# 清炒时蔬的做法

简单快手。

## 必备原料和工具

- 西兰花
- 大蒜

## 操作

- 热油下锅翻炒
"""
    parsed = parse_dish_markdown(md)
    assert parsed["ingredients"] == [
        {"ingredient_name": "西兰花", "quantity": None},
        {"ingredient_name": "大蒜", "quantity": None},
    ]
    assert parsed["steps"] == ["热油下锅翻炒"]


def test_parse_asterisk_bullets_and_colon_quantities():
    md = """# 凉拌木耳的做法

凉拌木耳，较为健康。

预估烹饪难度：★★

## 必备原料和工具

* 干木耳
* 蒜瓣

## 计算

每份（1 人量）:

* 干木耳: 20g / 湿木耳: 120g
* 蒜瓣: 2-3 个

## 操作

* 泡发干木耳
* 将蒜瓣切碎
"""
    parsed = parse_dish_markdown(md)
    assert parsed["difficulty"] == "简单"
    assert parsed["ingredients"] == [
        {"ingredient_name": "干木耳", "quantity": "20g / 湿木耳: 120g"},
        {"ingredient_name": "蒜瓣", "quantity": "2-3 个"},
    ]
    assert parsed["steps"] == ["泡发干木耳", "将蒜瓣切碎"]


def test_parse_strips_image_markdown_from_description():
    md = """# 小龙虾的做法

![成品](./成品.jpg)
在家里做的小龙虾，干净卫生。

## 操作

- 清洗小龙虾
"""
    parsed = parse_dish_markdown(md)
    assert parsed["description"] == "在家里做的小龙虾，干净卫生。"


def test_parse_numbered_steps_and_skips_comment_blockquote():
    md = """# 白灼菜心的做法

<!-- 标题必须是 `菜名` + `的做法`。 -->

> 没有拍照，上图是网图

白灼菜心是经典粤菜。

## 操作

1. 菜心洗净
2. 大蒜切成蒜末
3. 调制料汁
"""
    parsed = parse_dish_markdown(md)
    assert parsed["description"] == "白灼菜心是经典粤菜。"
    assert parsed["steps"] == ["菜心洗净", "大蒜切成蒜末", "调制料汁"]
