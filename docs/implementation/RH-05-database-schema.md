# RH-05 数据库 Schema 与 SQLite 建表

## 1. 一句话总结

用 SQLAlchemy 2.0 把 PRD 里的核心实体落成 9 张表（users / user_profiles / recipes / recipe_ingredients / recipe_steps / recipe_versions / cooking_records / menus / menu_recipe_drafts），配好引擎、会话和「启动即建表」，为后面菜谱 CRUD、推荐、菜单规划提供结构化存储底座。

## 2. 在项目中的位置

结构化业务数据（菜谱、食材用量、画像、菜单状态）全部走 SQLite；语义检索才走 Qdrant（RH-04）。这一层是「SQL 是菜谱归属、发布状态、点单权限的最终依据」这句约束的落地点。

- `backend/app/db/base.py` —— `Base`（DeclarativeBase）+ `utcnow()`。
- `backend/app/db/session.py` —— `engine`、`SessionLocal`、`get_db` 依赖、`init_db()`。
- `backend/app/models/` —— 按域拆成 `user.py` / `recipe.py` / `menu.py`，`__init__.py` 统一 import。
- `backend/app/main.py` —— lifespan 里调 `init_db()`，启动即建表。
- `scripts/init_db.py` —— 不启动服务时手动建表的入口。

## 3. 实现细节

### 3.1 表与关键字段

| 表 | 职责 | 关键设计 |
|---|---|---|
| `users` | 用户 | `openid` 唯一索引（本地演示用测试 ID） |
| `user_profiles` | 长期饮食画像 | `user_id` 唯一；偏好/忌口/过敏原用 JSON 数组 |
| `recipes` | 菜谱主表 | `owner_id` 可空=公共菜谱；`source_recipe_id` 记录导入来源 |
| `recipe_ingredients` | 食材 | `quantity` 用字符串，兼容「适量」「500克」 |
| `recipe_steps` | 步骤 | `step_number` 保序 |
| `recipe_versions` | 版本快照 | `parent_version_id` + `snapshot_json`，不覆盖原记录 |
| `cooking_records` | 制作记录 | `actual_ingredients_json` 等，是个人知识库来源 |
| `menus` | 菜单规划状态机 | 需求/已确认/已拒绝/候选全 JSON，多轮持久化 |
| `menu_recipe_drafts` | AI 新菜谱草稿 | `promoted_recipe_id` 空=还没转正 |

### 3.2 分层

- **`base.py`**：`class Base(DeclarativeBase)`；`utcnow()` 返回 naive UTC（SQLite 的 DateTime 不存时区）。
- **`session.py`**：`create_engine(settings.database_url, connect_args={"check_same_thread": False})`——SQLite 在多线程下必须关这个检查；`get_db()` 是 FastAPI 依赖，`yield` 完自动 close。
- **`init_db()`**：先 `from app import models` 触发所有模型注册，再 `Base.metadata.create_all(bind=engine)`，幂等。
- **关系**：`Recipe` ↔ `ingredients/steps`（级联删除 + 按 order 排序）、`User` ↔ `profile/recipes`、`Menu` ↔ `drafts`。用 `from __future__ import annotations` + 字符串类型注解解决前向引用。

## 4. 设计决策与权衡（面试重点）

- **为什么 `status` / `visibility` / `orderable` 三个字段分离？**
  - `status` 回答「这道菜做到哪一步了」（Draft/Imported/Cooked/Verified）；`visibility` 回答「能不能被别人看到」；`orderable` 回答「访客能不能点单」。
  - 三者语义完全不同，PRD 特别强调「公开不代表可点单」「导入不代表做过」。混在一个枚举里会导致权限判断出错——而「SQL 是权限的最终依据」，字段不分离权限就无从谈起。
- **公共菜谱和个人菜谱怎么区分？**
  - 用 `owner_id` 是否为空区分归属，而不是另建一张 `public_recipes` 表：字段几乎一致，拆表会重复维护两套 CRUD 和检索逻辑。
  - 导入时复制数据并写 `source_recipe_id`，用户改自己的副本不影响公共源（两行独立数据）。
- **`quantity` 为什么用字符串而不是 float？**
  - 中餐菜谱大量「适量」「少许」「半个」这类非数值表达，float 存不下。MVP 先保证「能展示」，Day6 算预算时再按食材名查价格字典估算，不用精确用量。
- **菜单的 `confirmed_dishes_json` 等为什么用 JSON 而不是拆表？**
  - 这些是「当前一轮对话的状态快照」，查询粒度是「整个菜单」而不是「单个已确认菜品」；拆表会让多轮状态更新变复杂（每次都要 diff 增删）。
  - 反例：`recipe_ingredients`/`recipe_steps` 要频繁单查、按序展示、参与食材汇总，所以拆成独立表。**原则：按「访问粒度」决定拆表还是 JSON。**
- **为什么用同步 SQLAlchemy + SQLite，不搞 async/aiosqlite？**
  - SQLite 本身就是单写者、本地文件库，async 拿不到多少吞吐收益；同步代码简单、好调试、好写测试。FastAPI 的 async 优势用在「等模型 API」这类 IO 上（RH 后面），不在本地 SQLite 上。真到了并发瓶颈再换 PostgreSQL + async，代价也可控。
- **为什么用 `create_all` 而不是 Alembic 迁移？**
  - 七天 MVP、单人开发、表结构还可能在 Day2~6 微调，`create_all` 最省事。Alembic 的价值在多环境/多人协作的增量迁移，MVP 阶段引入是「为技术名词增加复杂度」（计划明确禁止）。

## 5. 面试高频问题 & 回答要点

**Q1：为什么 SQLite 和 Qdrant 要分开存？各自存什么？**
要点：结构化精确数据（食材用量、权限、发布状态）进 SQLite——要精确查询、事务、做权限最终依据；语义相似的内容（菜谱描述、制作经验）进 Qdrant 向量库——要按语义召回。两者职责不同，向量库不能替代关系库。

**Q2：`check_same_thread=False` 是什么？为什么 SQLite 要加？**
要点：SQLite 默认一个连接只能在创建它的线程里用；FastAPI 把同步依赖丢进线程池，请求线程会变，不加就报 "objects created in a thread can only be used in that same thread"。加上让 SQLAlchemy 连接池可跨线程复用。

**Q3：什么时候用 JSON 列、什么时候拆子表？**
要点：看访问粒度。整读整写、不需要单独按子项查询/统计的（菜单状态快照）用 JSON；需要单查、排序、聚合的（食材、步骤）拆表。这是个通用取舍，面试常问。

**Q4：`source_recipe_id` 是干嘛的？**
要点：一键导入时保留「这个个人菜谱是从哪个公共菜谱来的」，用于溯源、去重（防止重复导入同一道菜）和展示来源；同时证明「导入是复制不是引用」——改个人副本不影响公共源。

**Q5：多轮菜单状态为什么要持久化到 SQLite？**
要点：菜单规划是多轮对话，用户刷新页面、小程序冷启动、后端重启后，已确认的菜品都不能丢。状态只有存后端数据库才能保证这一点，前端内存或浏览器缓存都不可靠。

## 6. 踩坑

- **前向引用**：`Recipe` 里写 `Mapped[list["RecipeIngredient"]]`，必须 `from __future__ import annotations`，且 `relationship()` 里用字符串 `"RecipeIngredient"`，否则模型互相 import 会循环引用报 `NameError`。
- **`init_db` 必须延迟 import models**：`Base.metadata.create_all` 前要确保所有模型都被 import 过，否则表会「静默少建」。所以 `init_db()` 里先 `from app import models`。
- **`.env` 相对路径**：`config.py` 的 `env_file=".env"` 相对启动目录，所以 `scripts/init_db.py` 里要先 `os.chdir` 到 `backend/`，否则读不到配置、库文件也建错位置。
- **`datetime.utcnow` 已弃用**：Python 3.12+ 会告警，改用自带的 `utcnow()`（`datetime.now(timezone.utc).replace(tzinfo=None)`），保证存的是无时区 UTC。
- **冒烟测试留脏数据**：验证后记得删 `recipehub.db`（它已被 `.gitignore` 忽略，是运行时产物），保持仓库只含代码。
