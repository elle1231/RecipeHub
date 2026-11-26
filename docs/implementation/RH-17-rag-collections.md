# RH-17 双知识库 Collection + 文档结构 + Embedding 维度定死

## 1. 一句话总结

在 `services/rag/` 里落地 RAG 的第二块地基：定义两个知识库的文档结构（Chunk 长什么样），按 `embedding_model` 的维度（BGE-small-zh-v1.5 → 512）幂等创建 `public_recipes` / `personal_kitchens` 两个 Qdrant Collection，并给个人库的 `user_id` 建好隔离索引，为 RH-19 写向量、RH-20 检索铺路。

## 2. 在项目中的位置

Day 3（双知识库与基础 RAG）的第一个交付。RH-04 只拿到了「连接」，RH-17 才真正把两个 Collection 建出来：

- `backend/app/services/rag/schemas.py` —— 文档结构：Collection 名 + 两个 Chunk 的 Pydantic 模型（Payload 字段约定）。
- `backend/app/services/rag/collections.py` —— 向量参数（维度/距离）+ `ensure_collections()` 幂等创建 + Payload 索引。
- `backend/app/services/rag/embedding.py` —— `EmbeddingService` 抽象 + `DeterministicEmbedding` 确定性桩（测试/无模型联调用）。
- `backend/app/core/config.py` —— 新增 `embedding_dim`（512，与 `embedding_model` 对应）。
- `scripts/init_collections.py` —— 手动初始化脚本（等价于启动时的 `ensure_collections()`）。
- `backend/app/main.py` —— lifespan 里幂等建 Collection，Qdrant 不可用时降级为告警不阻塞启动。
- `backend/tests/test_rag_collections.py`、`test_rag_embedding.py` —— 单元测试（mock QdrantClient，不依赖真实服务）。

## 3. 实现细节

- **schemas.py**：把「向量库里一个 Chunk 是什么」定死。
  - 两个 Collection 名：`public_recipes` / `personal_kitchens`（唯一出处，避免散落魔法字符串）。
  - `DocumentType` 枚举：公共库有 `recipe` / `ingredient_knowledge` / `cooking_skill`；个人库有 `personal_recipe` / `cooking_note` / `experience`。
  - `PublicRecipeChunk`：`document_id`（幂等主键）、`recipe_id`、`title`、`content`、`source`、`category`、`document_type`。
  - `PersonalKitchenChunk`：`user_id`（内部整数 `users.id`，与 `recipes.owner_id` 一致）、`recipe_id`、`title`、`content`、`version`、`verified`、`visibility`、`document_type`。
- **collections.py**：`ensure_collections(client)` 先 `collection_exists` 判断，不存在才 `create_collection`，并在「刚创建」的库上建 Payload 索引（幂等，重复调用不重复建索引）。
  - 向量参数：`VectorParams(size=settings.embedding_dim, distance=COSINE)`——维度不写死 512，而是从 `embedding_dim` 配置读，换模型改一处即可。
  - 公共库索引：`recipe_id`(integer)、`category`(keyword)、`document_type`(keyword)。
  - 个人库索引：`user_id`(integer)、`recipe_id`(integer)、`document_type`(keyword)、`visibility`(keyword)、`verified`(bool)。
- **embedding.py**：`EmbeddingService` 抽象类只约定 `dimension` + `embed_texts(texts) -> list[list[float]]`；`DeterministicEmbedding` 用 SHA-256 把文本映射到 512 维（同一文本永远同向量、不同文本几乎不碰撞），**明确标注不产生语义向量**，仅用于测试和打通链路。真实模型（本地 BGE / OpenAI 兼容 API）留到 RH-19 写向量时在 `get_embedding_service()` 里按 `settings` 切换。
- **main.py lifespan**：`init_db()` 后接 `_ensure_qdrant_collections()`，用 try/except 包裹——Qdrant 没起时只打 warning，不阻塞「干净环境 + SQLite」也能先把 API 跑起来。

## 4. 设计决策与权衡（面试重点）

- **为什么 Collection 维度不写死 512，而是读 `settings.embedding_dim`？**
  - 维度是模型的固有属性，不是业务常量。写死 512 会把「这个模型是 512 维」这个知识埋在代码里，换模型时容易漏改。集中到 config 一处，`VectorParams`、`DeterministicEmbedding` 都从它读，换模型改 `.env` 即可（但注意：维度变了要**重建** Collection，旧向量不兼容）。
- **为什么个人库的 `user_id` 用整数 `users.id` 而不是 openid 字符串？**
  - 与 SQL 的 `recipes.owner_id` 对齐。权限判定最终在 SQL（`get_or_create_user` 把 openid 映射到 `users.id`），Qdrant 的 `user_id` 过滤只是辅助加速。两处用同一个标识，才不会出现「SQL 用 id、向量库用 openid」两套口径对不上。
- **为什么 Payload 里存 `content` 原文？**
  - 检索最终要「把命中的文本拼成上下文喂给 LLM」。只存向量不存原文，检索回来还得回 SQL 查原文，多一跳。把 `content`（待向量化的正文）一并放进 Payload，RH-20 检索直接能拿到可展示/可拼接的文本。
- **为什么索引只在「刚创建」时建，而不是每次都建？**
  - 建索引本身幂等，但每次启动都发一堆 `create_payload_index` 请求是多余的网络开销。用 `created[name]` 判断只在新建时建，已存在的库跳过。代价是「给已有库后补索引」要手动做，但这属于 RH-19 写向量时的数据迁移范畴。
- **为什么 Qdrant 没起时不崩溃、只告警？**
  - SQLite 是硬依赖（业务数据），Qdrant 是软依赖（语义检索）。让「干净环境」在没起 Qdrant 时也能先跑 API，符合「先让最小链路跑通」的约束；真正要用向量时再 `scripts/init_collections.py` 补建即可。

## 5. 面试高频问题 & 回答要点

**Q1：两个 Collection 为什么要分开，而不是一个 Collection 加个 `source_type` 字段？**
要点：两类数据的权限模型和生命周期完全不同——公共菜谱全员可读、无用户维度；个人厨房必须按 `user_id` 隔离、有 `visibility`/`verified`/`version`。分开后各自建索引、各自过滤，检索时天然物理隔离，也避免「一个库既有公共又有私有、过滤条件漏写就串数据」的风险。PRD 也明确建议两个 Collection。

**Q2：距离度量为什么选 Cosine？**
要点：BGE 系列通常输出可归一化的向量，余弦相似度对向量长度不敏感、对「语义方向」敏感，是文本语义检索的主流选择。若换成 L2（欧氏距离），要先归一化向量，且对向量模长敏感，不如 Cosine 稳。

**Q3：`document_id` 为什么要设计成幂等主键？**
要点：写向量（RH-19）会重复跑（比如导入脚本重跑、个人菜谱更新后重新索引）。`document_id` 由「来源 + 菜谱 + 分片序号」拼出，重复 upsert 同一个 id 会覆盖而不是新增，避免同一道菜在库里堆出一堆重复点。

**Q4：为什么 Embedding 服务现在只有一个「确定性桩」，不直接上 BGE？**
要点：RH-17 的职责是「把 Collection 建出来、把维度/接口定死」，不依赖真实模型也能验收。真实模型（本地 BGE 要装 torch/sentence-transformers，或 OpenAI 兼容 API 要配 key）是 RH-19 写向量的前置，那里才真正「成批编码 169 道菜谱」。现在用确定性桩就能把 Collection→检索链路先打通，且不因模型不可用阻塞交付。

## 6. 踩坑

- **`collection_exists` 不是「连接测试」**：它本身会发请求，Qdrant 没起时直接抛异常。所以 lifespan 里要 try/except，否则起 app 会因 Qdrant 没起而崩。
- **测试不要依赖真实 Qdrant**：真实 Qdrant 是全局状态（Collection 是共享的），单元测试用 `MagicMock` 模拟 `collection_exists` / `create_collection`，保证任何机器（哪怕没起 Docker）都能跑绿；真实创建交给脚本手动验收。
- **换 embedding 模型 = 换维度 = 必须重建 Collection**：`qdrant-client` 会拒绝往维度不符的 Collection 写向量。这是「维度定死在 Collection、且由模型决定」的直接后果，别指望改个 `.env` 就能无缝换模型。
