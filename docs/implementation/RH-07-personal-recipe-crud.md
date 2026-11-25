# RH-07 个人菜谱 CRUD + 一键导入

## 1. 一句话总结

把 RH-06 定的契约从 501 占位落成真业务：`service` 层实现个人菜谱的增删改查与「公共菜谱一键导入」，所有操作按 `owner_id` 隔离，让用户在小程序里创建、刷新后仍能从后端取回自己的菜谱。

## 2. 在项目中的位置

Day 2 第一个业务模块，也是「我的厨房」的地基。它是第一个真正读写 SQLite 的模块，确立了「api 薄、service 厚」的分层，后面 RH-08（公共菜谱）、RH-09（画像）都复用同一套约定。

- `backend/app/api/recipes.py` —— 路由层：解析请求头/参数，调 service，本身无业务。
- `backend/app/services/recipe/service.py` —— 业务层：CRUD + 导入的全部逻辑。
- `backend/app/services/user/service.py` —— `get_or_create_user`，openid → users.id 映射。
- `backend/tests/test_recipes.py` —— 13 条接口测试（含权限隔离、重复导入）。
- `backend/tests/conftest.py` —— 测试夹具：每个测试独立临时 SQLite，不污染开发库。

## 3. 实现细节

### 3.1 分层与数据流

```
请求头 X-User-Id (openid 字符串)
        ↓  get_or_create_user(db, openid)  → users.id
        ↓  service 按 owner_id 隔离操作
SQLite (recipes / recipe_ingredients / recipe_steps)
        ↓  RecipeRead (from_attributes) 自动序列化嵌套食材/步骤
```

### 3.2 六个接口

| 方法 | 路径 | 行为 | 关键点 |
|---|---|---|---|
| GET | `/api/recipes` | 个人菜谱列表 | `owner_id == user.id`，按 `updated_at` 倒序，`skip/limit` 分页 |
| POST | `/api/recipes` | 创建 | 默认 `status=Draft`/`visibility=private`/`orderable=False`，主信息+食材+步骤一次提交 |
| GET | `/api/recipes/{id}` | 详情 | 含嵌套食材/步骤 |
| PUT | `/api/recipes/{id}` | 部分更新 | 只改传入字段；食材/步骤传了则整体替换 |
| DELETE | `/api/recipes/{id}` | 删除 | 级联删食材/步骤 |
| POST | `/api/recipes/import` | 一键导入 | 复制公共菜谱为个人副本 |

### 3.3 导入流程（对应 PLAN 11.1）

1. `source = db.get(Recipe, source_recipe_id)`，校验 `owner_id is None` 才叫「公共菜谱」，否则 404。
2. 按 `owner_id + source_recipe_id` 查重，已导入则 **409**（带原个人菜谱 id）。
3. 复制主信息 + 食材 + 步骤，写 `source_recipe_id`，`status="Imported"`，`visibility="private"`。
4. 返回新个人菜谱 id。

## 4. 设计决策与权衡（面试重点）

- **为什么 `owner_id` 隔离，越权统一返回 404 而不是 403？**
  - 404 不泄露「别人的菜谱是否存在」这个信息。403 等于承认「这条数据存在但你无权访问」，对攻击者来说是在枚举资源。安全上「不存在」和「无权访问」对外表现一致是更好的默认。

- **为什么 api 层薄、service 层厚？**
  - 路由只做「参数进、响应出」，业务（校验、复制、去重、状态赋值）全在 service。好处：① 接口测试可以直接调 service 单测，不用起 HTTP；② 后面 RAG/推荐/菜单规划都要复用「取用户菜谱」这类逻辑，不绑死在路由上；③ 符合计划里「API、数据模型、业务服务分离」的约束。

- **为什么部分更新用 `model_dump(exclude_unset=True)`？**
  - `RecipeUpdate` 全字段可选。`exclude_unset` 只保留「客户端这次显式传了」的字段，未传的不动，实现 PATCH 语义。若用 `exclude_none` 会把「显式传 null 想清空」和「没传」混为一谈，误清空字段。

- **为什么导入是「复制」而不是「引用」？**
  - 复制生成新行，`source_recipe_id` 只做溯源。用户改自己的副本，公共菜谱不受影响——这正是 PRD「导入后的个人菜谱与公共菜谱相互独立」的要求。若用引用（外键指向公共菜谱），用户一改就污染了公共数据，且无法承载「个人备注、用量微调」这类私有差异。

- **为什么 openid 要映射成 users.id，不能直接当 owner_id？**
  - 请求头里只有 openid（字符串，本地演示的临时身份），而 `recipes.owner_id` 是指向 `users.id` 的整型外键。两者语义不同：openid 是「微信侧身份」，users.id 是「应用内主键」。用 `get_or_create_user` 做桥接，还能顺手解决「首次请求自动建用户」，避免手动初始化测试用户。

- **为什么食材/步骤「整体替换」而不是「增量 diff」？**
  - 菜谱编辑是「用户改完一版整道菜再保存」，不是「在旧列表上增删一行」。整体替换语义清晰、实现简单；增量 diff 要处理「哪条改了、哪条删了、顺序怎么变」，对 MVP 是过度设计。版本管理（P1）会单独做快照，不靠这里的 diff。

## 5. 面试高频问题 & 回答要点

**Q1：你的个人菜谱 CRUD 是怎么做权限隔离的？**
要点：所有查询/修改/删除都以 `owner_id == 当前用户 id` 为前提，越权统一 404 不泄露资源存在性。用户身份从 `X-User-Id` 头拿到 openid，经 `get_or_create_user` 映射成 `users.id`，不信任客户端直接传 user_id。

**Q2：一键导入怎么保证「不重复导入」和「相互独立」？**
要点：去重靠 `owner_id + source_recipe_id` 唯一性查重，命中返回 409；独立靠「复制整份数据成新行」而非引用，`source_recipe_id` 只做溯源，用户改副本不影响公共源。

**Q3：部分更新（PATCH 语义）是怎么实现的？**
要点：`RecipeUpdate` 全字段可选，`model_dump(exclude_unset=True)` 只取显式传入字段，未传的保持原值；嵌套的食材/步骤用「传了则整体替换、传 None 则不动」区分。

**Q4：为什么要拆 service 层，直接在路由里写不行吗？**
要点：路由只做参数与响应，业务逻辑独立可复用、可单测；后续推荐、菜单规划都要复用「按用户取菜谱」的能力，不拆会在路由里重复写一遍权限判断。

## 6. 踩坑

- **`model_dump` 会把嵌套 Pydantic 模型变成 dict**：`payload.model_dump()` 后，`ingredients` 是 `list[dict]`，再按 `.sort_order` 访问会 `AttributeError`。正确做法是标量字段用 `exclude={"ingredients","steps"}` 后 dump，嵌套字段直接读原始对象 `payload.ingredients`（还是 Pydantic 对象）。

- **测试数据库隔离**：测试直接打真实 `recipehub.db` 会留脏数据（RH-05 踩坑里也提过）。用 `tmp_path` 建临时 SQLite + `app.dependency_overrides[get_db]` 覆盖，每个测试独立、跑完即弃。

- **`expire_on_commit=False` 的价值**：`sessionmaker(..., expire_on_commit=False)` 让 `db.commit()` 后 ORM 对象不回退为「已过期」，`created_at`/`updated_at`/自增 `id` 在 commit 时已回填到对象上，直接返回给 `response_model` 序列化即可，不必再 `db.refresh`（refresh 还可能连带 expire 关系集合）。

- **重复导入的 409 要带上已有 id**：`detail` 里带上 `existing.id`，前端能据此直接跳转或提示「已在你的厨房里」，而不是让用户再找一遍。

- **`from app.services.recipe import service` 的写法**：`service` 是包里的子模块，`from 包 import 子模块` 会触发子模块导入；比 `from ...service import create_recipe, ...` 逐项列更能避免以后加函数时漏 import。
