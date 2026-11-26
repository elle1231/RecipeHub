# RH-18 数据切分策略（Chunking）

## 1. 一句话总结

在 `services/rag/chunking.py` 落地切分策略：把一道菜谱的「标题 + 描述 + 食材 + 步骤」切成适合向量化的 Chunk——短菜谱整体一块，长菜谱按「概览 + 有序步骤」切块，每块带标题前缀、保留溯源 metadata、`document_id` 幂等可覆盖，为 RH-19 写向量提供纯函数。

## 2. 在项目中的位置

Day 3 的第二个交付，衔接 RH-17（Collection + 文档结构）与 RH-19（Embedding + 写向量）：

- `backend/app/services/rag/chunking.py` —— 切分核心 + 结构化字段格式化 + 组装 Chunk。
- `backend/app/services/rag/schemas.py` —— 给 `PublicRecipeChunk` / `PersonalKitchenChunk` 补 `chunk_index` / `total_chunks` 两个字段。
- `scripts/preview_chunking.py` —— 读真实 SQLite 公共菜谱跑一遍切分，输出统计与样例（人工验收切分质量）。
- `backend/tests/test_rag_chunking.py` —— 12 个单元测试。

## 3. 实现细节

- **格式化**：`format_ingredient` 把「番茄 + 2 + 个」拼成「番茄 2个」，数量与单位相连不留空格（中文习惯）；`format_step` 把「翻炒 + 大火 + 3分钟」拼成「翻炒（大火，约 3 分钟）」，缺失字段省略。用 `getattr` 鸭子类型，ORM 对象 / 测试桩都能传。
- **核心切分 `chunk_recipe_text`**：
  - 无步骤 → 单块（概览：标题+描述+食材）。
  - 整体 ≤ `MAX_CHUNK_CHARS`（800 字）→ 单块（完整正文）。
  - 超长 → 首块 = 概览，步骤按顺序打包，每块以 `【标题】\n步骤：` 开头，超限开新块。
- **组装**：`build_public_chunks` / `build_personal_recipe_chunks` / `build_cooking_note_chunks` 把切出的正文套上 metadata，生成 Pydantic Chunk。
  - `document_id` 格式：`public_recipe_{id}#{i}`、`personal_recipe_{user_id}_{recipe_id}#{i}`、`cooking_note_{user_id}_{record_id}#{i}`——`{i}` 是 0 起始块序号，RH-19 重复 upsert 同 id 即幂等覆盖。
  - 制作记录默认一条一块（`verified=True`、`document_type=COOKING_NOTE`），超长按段落累积切块。

## 4. 设计决策与权衡（面试重点）

- **为什么 Chunk 上限取 800 字而不是 512 token 精确换算？**
  - BGE-small-zh-v1.5 上限 512 token，中文 1 字约 1~2 token，800 字偏保守。切分是「宁可多切一点也不截断语义」，且 800 是字符粗算、跨模型更稳；真要精确 token 控制，应在 RH-19 embedding 时按 tokenizer 数。实测 169 条菜谱 avg 421 字、max 795 字，0 条超限，说明 800 足够容纳绝大多数菜谱。
- **为什么长菜谱「首块 = 概览，步骤另切」而不是简单按字符数硬切？**
  - 硬切会把「这是哪道菜、需要什么」和「怎么做」切散。概览（标题+描述+食材）是菜谱的「身份 + 前置条件」，单独成块能让检索命中「低脂高蛋白的菜」时直接回到完整概览；步骤块每块带标题前缀，保证「步骤 7 放多少盐」这类命中也知道属于哪道菜。这正是 PLAN 里「避免失去上下文的碎片」的落地。
- **为什么 `document_id` 要设计成可预测、幂等？**
  - 写向量会反复跑（公共菜谱重导、个人菜谱更新重索引）。`document_id` 由稳定字段（菜谱 id / 用户 id / 记录 id）+ 块序号拼出，重复 upsert 同 id 是覆盖而非新增，避免同一条菜谱在库里堆重复点。这一点在 RH-17 就定下了，这里落地。
- **为什么 chunking 是纯函数、不碰 ORM 和 Qdrant？**
  - 切分是最容易出边界 bug 的部分（长文本、步骤顺序、单步超长），纯函数无 IO 能像普通单元测试一样覆盖。延续 RH-07/RH-10 的「service 厚、壳薄」——RH-19 的脚本只做「读库 → 组装 → 调切分 → 调 embedding → upsert」的编排。

## 5. 面试高频问题 & 回答要点

**Q1：为什么不是「一个菜谱 = 一个向量」而是允许切多块？**
要点：长菜谱（十几步、上千字）整体塞进一个向量会超出 embedding 模型 token 上限，且「语义」会被稀释——步骤后半段和食材的相似度权重被前半段淹没。切多块能让每块聚焦、检索更准；但也不该切太碎（每个步骤一块），否则丢上下文。所以用「整体优先、超长才切」的折中。

**Q2：步骤切块怎么保证顺序不丢？**
要点：步骤本来就有 `step_number` 顺序，切块时按序累积、超限才开新块，绝不打乱顺序；每块都带 `【标题】` 前缀，即使跨块也能知道属于哪道菜、上下文没断。

**Q3：制作记录和个人菜谱怎么区分 document_type？**
要点：个人菜谱是 `personal_recipe`，制作记录/经验是 `cooking_note`，公共菜谱是 `recipe`。检索时按 `document_type` 过滤，就能分别召回「菜谱正文」还是「个人经验」，回答口径不同。

**Q4：切分策略为什么要「人工预览脚本」验收？**
要点：切分质量靠统计（平均块数、块大小分布、超限数）只看得见「量」，看不见「是否切散语义」。`preview_chunking.py` 打印真实样例，人工看一遍就知道有没有「步骤串味」「食材被切断」这类问题，比单测更能兜住数据质量。

## 6. 踩坑

- **`quantity` 里混进了 `=` 前缀和备注**：RH-10 解析器把「小龙虾 = 2 斤（这是平时炒菜 3 倍量）」整体存进了 `quantity`（值为 `= 2 斤（…）`），导致 chunk 里出现「小龙虾 = 2 斤（…）」这种不干净文本。这是 **RH-10 数据清洗的遗留问题**，不是 RH-18 切分引入的——切分只是忠实格式化 DB 里的值。要不要清理 `=` 前缀、把备注拆回 `optional_note`，属于数据质量回填，可单独排。
- **单步超长会把一块撑爆**：如果某一步本身 > 800 字，`chunk_recipe_text` 的打包逻辑会把它单独放进一块（`current_len + added > max_chars` 且 `current_lines > 1` 才切，单步时直接塞入），结果该块可能略超上限。实测 169 条没触发，但极端长文（比如一段超长制作经验）可能超。当前策略优先保证「不切断单步」，牺牲「严格不超限」。
- **`format_ingredient` 的数量/单位拼接**：数量与单位要相连（「2个」）而不是空格隔开（「2 个」），否则中文读起来别扭。用 `f"{quantity or ''}{unit or ''}"` 直接拼接，别用 `" ".join`（会多出空格）。
