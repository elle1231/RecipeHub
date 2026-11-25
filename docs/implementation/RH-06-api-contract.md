# RH-06 第一版 API 契约

## 1. 一句话总结

用 Pydantic 把「菜谱 / 画像 / 一键导入」的请求响应结构定死，用 FastAPI 路由把 URL、方法、参数、状态码登记进 Swagger，先立契约、后写业务（业务在 Day 2）。

## 2. 在项目中的位置

契约是前后端之间的「合同」：前端按 Schema 发请求、解析响应，后端按 Schema 校验、返回。这里定的结构，Day 2 的 service 直接复用，避免前后端各写一套字段。

- `backend/app/schemas/` —— 请求/响应 Pydantic 模型（数据形状）。
- `backend/app/api/` —— 路由层（URL、方法、参数、状态码、`response_model`）。
- `backend/app/api/deps.py` —— `get_current_user_id` 依赖。
- `backend/app/main.py` —— `include_router` 把三个 router 挂到 app 上。

## 3. 实现细节

### 3.1 Schema 设计（`schemas/`）

- **Create / Update / Read 三类分离**：`RecipeCreate`（建）、`RecipeUpdate`（全字段可选，部分更新）、`RecipeRead`（带 id/状态/时间戳 + 嵌套食材步骤）。
- **嵌套结构**：`RecipeCreate` 里 `ingredients` / `steps` 是子模型列表，一次请求提交整道菜。
- **`from_attributes=True`**：`RecipeRead` / `UserProfileRead` / 子项 Read 都开了 ORM 模式，Day 2 直接从 SQLAlchemy 对象转响应，不用手写字段搬运。
- **`quantity` 用字符串**：和 RH-05 的 DB 一致，兼容「适量」「500克」。

### 3.2 路由契约（`api/`）

| 方法 | 路径 | 请求 | 响应 | 说明 |
|---|---|---|---|---|
| GET | `/api/recipes` | `skip`,`limit`,`X-User-Id` | `list[RecipeRead]` | 个人菜谱列表 |
| POST | `/api/recipes` | `RecipeCreate` | `RecipeRead`(201) | 创建菜谱 |
| GET | `/api/recipes/{id}` | `X-User-Id` | `RecipeRead` | 菜谱详情 |
| PUT | `/api/recipes/{id}` | `RecipeUpdate` | `RecipeRead` | 更新菜谱 |
| DELETE | `/api/recipes/{id}` | `X-User-Id` | 204 | 删除菜谱 |
| POST | `/api/recipes/import` | `RecipeImportRequest` | `RecipeImportResponse` | 一键导入 |
| GET | `/api/public-recipes` | `skip`,`limit`,`q`,`category`,`cuisine` | `list[RecipeRead]` | 公共菜谱列表/搜索/筛选 |
| GET | `/api/public-recipes/{id}` | — | `RecipeRead` | 公共菜谱详情 |
| GET | `/api/users/profile` | `X-User-Id` | `UserProfileRead` | 获取画像 |
| PUT | `/api/users/profile` | `UserProfileUpdate` | `UserProfileRead` | 更新画像 |

- 全部接口当前返回 **501 + 明确信息**（「接口契约已定义，业务逻辑在 Day 2 实现」），不假装修好；但 Pydantic 校验已生效（非法 body 返回 422）。
- 用户标识用请求头 `X-User-Id`（默认 `demo_user`），是本地演示阶段的临时方案，正式登录后换成解析后端 token。
- 路由顺序：`/import` 声明在 `/{recipe_id}` 之前，避免被路径参数吞掉。

## 4. 设计决策与权衡（面试重点）

- **为什么契约先行、业务后置？**
  - 计划 Day 1 目标就是「明确数据模型和核心 API 契约，避免后续架构返工」。先定死字段，前后端（小程序和 FastAPI）能并行开发、各自 mock；Day 2 写业务时不用再回头协商字段名。
- **为什么 Create/Update/Read 分开，而不是一个模型复用？**
  - 三种场景约束不同：Create 有必填（title、steps）、Update 全可选（部分更新，`None` = 不改）、Read 带数据库生成字段（id、时间戳、status）。混用会要么「更新时被迫传全量」要么「读取时泄露可写字段」。这也是 Pydantic 的经典用法。
- **为什么 501 占位而不是直接实现？**
  - Day 1 交付物是「契约初稿」，不是功能。501 让 Swagger 里契约可见、可被前端对照 mock，同时诚实标记「还没实现」，避免把空实现误当已完成。
- **为什么用户标识走 `X-User-Id` 头而不是路径参数？**
  - 用户身份是横切关注点，属于「上下文」而不是「资源定位」，放 header（或未来 token）比塞进每个路径更干净；也方便之后无缝换成认证中间件，不改路由签名。
- **为什么列表接口带 `skip`/`limit` 而不是一次返回全部？**
  - 分页是列表接口的通用约束，Day 1 就定下来避免 Day 2 前端拿到几千条数据再改。搜索/筛选参数已在 Day 2（RH-08）以 Query Parameters（`q`/`category`/`cuisine`）加入。

## 5. 面试高频问题 & 回答要点

**Q1：你的 API 契约是怎么设计的？**
要点：Pydantic 定数据形状（Create/Update/Read 分离、嵌套、ORM 模式）+ FastAPI 路由定 URL/方法/状态码，OpenAPI 自动生成，前端照此 mock、后端照此校验。

**Q2：Pydantic 的 `from_attributes` 是干嘛的？**
要点：旧版的 `orm_mode`。开了之后能从 SQLAlchemy ORM 对象直接构造响应模型，省去手动 `RecipeRead(id=r.id, ...)` 的字段搬运，尤其嵌套结构（食材/步骤）会递归转换。

**Q3：为什么更新接口用全可选字段？**
要点：实现 PATCH 语义——前端只传要改的字段，未传的保持原值。比「必须传全量」更安全（不会误清空没传的字段），也符合前端表单局部保存的习惯。

**Q4：如何区分「请求校验错误」和「业务未实现」？**
要点：校验错误是 422（Pydantic 在进业务前拦截），业务未实现是 501（契约存在但逻辑没写）。两者在 HTTP 层就区分开，前端能据此给不同提示。

## 6. 踩坑

- **`/import` 与 `/{recipe_id}` 的路由顺序**：静态路径要声明在动态路径之前，否则 `/import` 可能被 `{recipe_id}` 匹配（虽然类型是 int 会 422，但语义上应显式让静态路径优先）。
- **`from __future__ import annotations` 与 Pydantic v2**：模型里用 `list[RecipeIngredientCreate]` 这类未来注解没问题，但别和旧版 `List[...]` 混用，统一用内置泛型。
- **header 默认值**：`Header(default="demo_user", alias="X-User-Id")` 里的 alias 让 Python 变量名（`x_user_id`）和 HTTP 头名（`X-User-Id`）解耦，别省 alias，否则 FastAPI 会按变量名找 `X-User-Id` 失败。
