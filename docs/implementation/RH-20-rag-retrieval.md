# RH-20 基础检索服务（公共 + 个人，user_id 隔离）

## 1. 一句话总结

在 `services/rag/retrieval.py` 实现检索服务：公共知识库语义检索、个人知识库语义检索（强制按 `user_id` 过滤隔离）、合并去重、返回带来源的文档内容。同时给 EmbeddingService 加 `embed_query`（BGE 查询加指令前缀），提升检索相关性。

## 2. 在项目中的位置

Day 3 的第四个交付，接 RH-19 写好的向量，供 RH-21 RAG Chain 消费：

- `backend/app/services/rag/retrieval.py` —— `search_public` / `search_personal` / `search`（合并）+ `RetrievedChunk` 结果模型。
- `backend/app/services/rag/embedding.py` —— 加 `embed_query` 方法（BGE 查询侧指令前缀）。
- `backend/tests/test_rag_retrieval.py` —— 4 个单元测试。

## 3. 实现细节

- **`RetrievedChunk`**：检索命中的扁平结果模型，含 `document_id` / `score` / `title` / `content` / `document_type` / `collection`，以及公共字段（`recipe_id`/`source`/`category`）和个人字段（`user_id`/`version`/`verified`/`visibility`）。`content` 原文来自 RH-19 写进 payload 的正文，上层拼上下文时直接取用，不回查 SQL。
- **`search_public`**：`embed_query(query)` → `client.query_points(PUBLIC_COLLECTION, query, limit)`。
- **`search_personal`**：多一个 `user_id` 参数，`query_filter = Filter(must=[FieldCondition(user_id == user_id)])` 硬过滤个人知识。
- **`search`**：同时查两个库，返回 `{"public": [...], "personal": [...], "merged": [...]}`；merged 按 score 降序、document_id 去重。
- **`embed_query`**：默认等价 `embed_texts([q])[0]`；`LocalBgeEmbedding` 覆写为加 `BGE_QUERY_PREFIX`（`为这个句子生成表示以用于检索相关文章：`）——BGE 的「查询侧加指令、文档侧不加」不对称编码，相关性更好。

## 4. 设计决策与权衡（面试重点）

- **为什么 `user_id` 是服务函数参数，而不是让客户端传？**
  - 这是「不得通过请求参数读他人数据」的落地：检索服务的调用方（后续 API 层）必须先 `openid → users.id`，再把内部 id 传进来；客户端拿不到也传不进别人的 `user_id`。Qdrant 的 payload filter 是「第一道闸」，真正的权限判定后续仍以 SQL 为准（RH-44 二次校验）。
- **为什么 Qdrant filter 用 `FieldCondition` 而不是在代码里手动过滤？**
  - `user_id` 在 RH-17 已建了 integer 索引，`FieldCondition` 让 Qdrant 在向量检索时同时走索引过滤，既快又不会把别人数据捞出来。手动过滤要先把候选全取出来再筛，既慢又暴露了不该拿到的数据。
- **为什么 BGE 查询要加指令前缀？**
  - BGE 是「检索」场景训练的：文档侧和查询侧用不对称编码（查询加 `为这个句子生成表示以用于检索相关文章：`），能显著提升短 query 的相关性。文档侧（RH-19 索引）不加，查询侧加，两者分开。
- **为什么 merged 去重只做到 document_id 级别？**
  - document_id 是全局唯一（RH-17/18 定死），跨库前缀不同天然不冲突，所以「同一 chunk 重复」不可能发生。更细的「同一道菜公共一份 + 个人导入一份」去重属于业务语义，留到 RH-21 上下文构建 / RH-24 推荐按需处理，这里不越界。

## 5. 面试高频问题 & 回答要点

**Q1：个人检索怎么做到用户隔离？**
要点：服务函数强制要 `user_id`（后端从登录态解析出的内部 id），检索时用 Qdrant `FieldCondition(user_id==x)` 硬过滤，用户 A 拿不到 B 的点。且 `user_id` 不是请求参数，客户端无法指定他人 id。

**Q2：返回结果里为什么要带 `content` 原文？**
要点：RAG 最终要把命中的文本拼成上下文喂 LLM。RH-19 已把原文写进 payload，这里直接 `hit.payload["content"]` 返回，上层无需按 recipe_id 回查 SQL 重拼，省一跳。

**Q3：`embed_query` 和 `embed_texts` 为什么要分开？**
要点：BGE 检索场景查询侧要加指令前缀、文档侧不加。分开两个方法让「索引」和「检索」各自用对编码方式，避免把文档也带上查询前缀（那样会损害索引质量）。

## 6. 踩坑

- **qdrant-client 1.20 的检索 API 是 `query_points` 不是 `search`**：`client.search(...)` 在旧版才有，1.20 已改名 `query_points(collection_name, query, query_filter, limit)`，返回 `QueryResponse.points`（每个 `ScoredPoint` 有 `.score` 和 `.payload`）。
- **`FieldCondition` 的 `match` 参数**：`models.FieldCondition(key="user_id", match=models.MatchValue(value=user_id))`，value 要和 payload 里的类型一致（这里 user_id 是 int，RH-17 建的是 integer 索引）。

## 7. 验证

- 全量测试 69 通过（新增 4 个检索测试）。
- 真实 Qdrant + 本地 BGE 冒烟：
  - 公共检索「番茄炒蛋怎么做」→ 西葫芦炒鸡蛋 / 炒滑蛋 / 洋葱炒鸡蛋（蛋类，相关）。
  - 个人检索：`user_id=3` 查「鸡蛋羹」命中其 `鸡蛋羹`（user_id=3）；`user_id=1` 查「鸡蛋羹」命中 0 条——**隔离生效**。
  - 合并检索正常返回分库 + merged。
