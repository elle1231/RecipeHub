# RH-08 公共菜谱列表 + 详情 + 搜索/筛选

## 1. 一句话总结

公共菜谱和个人菜谱共用一张 `recipes` 表、共用一个 `RecipeRead` 结构，靠 `owner_id IS NULL` 划出「菜谱大全」；本模块实现公共菜谱的分页列表、详情、关键词搜索和分类/菜系筛选，且绝不把个人菜谱漏出去。

## 2. 在项目中的位置

「菜谱大全」是用户发现菜品、一键导入个人厨房的入口，也是后面 RH-10 公共数据入库后直接被消费的查询接口。它与 RH-07（个人菜谱）是「同一张表、两条读写路径」——归属不同、业务规则不同，所以拆成两个 service，但共用 ORM 模型和 Schema。

- `backend/app/api/public_recipes.py` —— 路由：列表（带 `q/category/cuisine`）+ 详情。
- `backend/app/services/recipe/public_service.py` —— 业务：所有查询强制 `owner_id IS NULL`。
- `backend/tests/test_public_recipes.py` —— 10 条接口测试（含「个人菜谱不泄露」）。

## 3. 实现细节

### 3.1 接口

| 方法 | 路径 | 参数 | 说明 |
|---|---|---|---|
| GET | `/api/public-recipes` | `skip`/`limit`/`q`/`category`/`cuisine` | 分页 + 关键词搜索 + 分类/菜系筛选 |
| GET | `/api/public-recipes/{id}` | — | 详情（含食材/步骤） |

### 3.2 查询逻辑

```text
select Recipe where owner_id IS NULL        -- 硬性条件：只取公共菜谱
        [and (title LIKE %q% or description LIKE %q%)]   -- 关键词
        [and category == category]                        -- 分类筛选
        [and cuisine == cuisine]                          -- 菜系筛选
order by id desc, offset skip, limit limit
```

- 筛选参数都是**可选**的，不传就不加对应 `where`（条件式拼接，不是拼接 SQL 字符串，无注入风险）。
- 关键词用 `LIKE '%q%'`，同时命中标题和描述（SQLite 的 `LIKE` 对 ASCII 不区分大小写，中文无大小写问题）。

## 4. 设计决策与权衡（面试重点）

- **为什么公共菜谱不单独建 `public_recipes` 表？**
  - 字段几乎一致（标题/描述/图片/分类/菜系/耗时/难度 + 食材/步骤），拆表要维护两套几乎一样的 CRUD、检索和序列化逻辑。用 `owner_id IS NULL` 区分归属（RH-05 就定了这个模型），一行数据既能当公共菜谱又能被复制成个人菜谱，还天然支持「导入 = 复制新行 + source_recipe_id 溯源」。

- **为什么公共接口要显式 `owner_id IS NULL`，而不是相信调用方？**
  - 「SQL 是菜谱归属的最终依据」——公共接口一旦漏了这个条件，某个用户 id 被误传进来，个人菜谱就会直接出现在菜谱大全里。把它写成硬性过滤条件（而非「可选参数」），是权限边界，不是展示偏好。

- **为什么搜索参数用 `LIKE` 而不是全文检索 / 向量检索？**
  - MVP 阶段数据量（几十到几百条）用 `LIKE` 足够快、零额外依赖。语义检索（「想吃清淡的」这种模糊意图）是 Day 3 的 Qdrant 向量检索要解决的，两者职责不同：这里解决「精确关键词/分类」的确定性查询，Qdrant 解决「语义相似」的召回。

- **为什么搜索走列表接口的 query 参数，而不是单独 `/search` 端点？**
  - 搜索和列表本质是同一资源集合的不同过滤视图，合并成一个端点 + 可选参数最 RESTful，也避免 `/search` 和 `/{id}` 的路由顺序坑（RH-06 踩坑里刚提过）。PRD 里列了 `/search` 是规划草案，落地时以「少一个端点、少一份维护」为准。

- **为什么筛选是「精确匹配」而不是「模糊匹配」？**
  - `category`/`cuisine` 是枚举式字段（前端下拉框给固定值），精确匹配才稳定。模糊匹配会把「家常菜」和「家常菜改良」混在一起。真正需要模糊的是用户自由输入的关键词 `q`，那个用 `LIKE`。

## 5. 面试高频问题 & 回答要点

**Q1：公共菜谱和个人菜谱在数据层怎么区分？**
要点：同一张 `recipes` 表，`owner_id IS NULL` = 公共菜谱，`owner_id = 用户id` = 个人菜谱；导入时复制成新行并写 `source_recipe_id` 溯源，两边互不影响。

**Q2：怎么做关键词搜索和筛选？**
要点：列表接口的可选 query 参数——`q` 用 `LIKE` 命中标题/描述，`category`/`cuisine` 精确匹配；条件式拼接 `where`，不传就不加，不拼 SQL 字符串避免注入。

**Q3：怎么保证公共接口不会泄露个人菜谱？**
要点：查询硬性加 `owner_id IS NULL`，是权限边界而非展示偏好；测试里专门有一条「个人菜谱不出现在公共列表、个人 id 走公共详情返回 404」。

## 6. 踩坑

- **`description` 为 NULL 时 `LIKE` 的结果**：`NULL LIKE '%x%'` 返回 NULL（不是 False），`or_(title.like, description.like)` 里 title 不命中、description 为 NULL 时整体是 NULL 而非 True/False，好在 SQL 把 NULL 当「不成立」处理，逻辑仍正确——但要清楚这一点，别在别处写 `where(description.like(...))` 单条时误以为能兜住空值。

- **公共列表的顺序**：用 `id desc`（新入库在前）做稳定排序。若按 `updated_at` 排，公共菜谱没有「更新」场景，字段常为建库时间，排序意义不大且不稳定。

- **测试隔离个人菜谱**：`test_list_excludes_personal_recipes` 里先建个人菜谱再断言公共列表为空，专门兜住「忘了写 `owner_id IS NULL`」这类高危回归——这类权限边界测试比功能测试更值钱。

- **共用 helper 的边界**：公共菜谱 seed 的 `visibility="public"` 只是语义上的「公开」，真正的「公共」判据始终是 `owner_id IS NULL`；别把 `visibility` 当成「是否属于菜谱大全」的依据（visibility 是个人菜谱是否分享给别人的开关，两码事）。
