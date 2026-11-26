# RH-19 Embedding 与向量写入脚本

## 1. 一句话总结

把 RH-17 的「确定性桩」换成真实 Embedding（本地 BGE / OpenAI 兼容 API），并实现 `scripts/build_vector_index.py`：读 SQLite → Chunking（RH-18）→ Embedding → Qdrant Upsert，公共菜谱进 `public_recipes`、个人菜谱+制作记录进 `personal_kitchens`，point id 由 `document_id` 确定性生成、可幂等覆盖。

## 2. 在项目中的位置

Day 3 的第三个交付，接 RH-18 的切分，供 RH-20 检索消费：

- `backend/app/services/rag/embedding.py` —— 补全三种真实后端 + 工厂选择。
- `backend/app/services/rag/index.py` —— 采集（SQLite→Chunk）+ 写入（Embedding→Upsert）编排。
- `scripts/build_vector_index.py` —— 薄 CLI 壳。
- `backend/requirements.txt` —— 新增 `sentence-transformers`（本地 BGE 后端）。
- `backend/tests/test_rag_index.py` —— 6 个单元测试（采集真跑临时库，写入用 mock Qdrant + 确定性桩）。

## 3. 实现细节

- **embedding.py 三种后端**，都实现 `EmbeddingService`（`dimension` + `embed_texts`）：
  - `LocalBgeEmbedding`：惰性加载 `sentence_transformers.SentenceTransformer(settings.embedding_model)`，`normalize_embeddings=True`（配合 Cosine），默认 BGE-small-zh-v1.5（512 维）。
  - `OpenAICompatEmbedding`：用 httpx 直连 `{base_url}/embeddings`（不额外引入 openai 包），按 `index` 排序保证与输入顺序一致，兼容任意 OpenAI 协议服务。
  - `DeterministicEmbedding`：保留，仅测试 / 无模型联调。
  - `get_embedding_service()` 优先级：配了 key+base_url → OpenAI 兼容 API；装了 sentence-transformers → 本地 BGE；否则 → 确定性桩并告警。
- **index.py**：
  - `collect_public_chunks` / `collect_personal_chunks`：从 SQLite 读公共/个人菜谱与制作记录，复用 RH-18 的切分函数。
  - `embed_and_upsert`：批量 embed → 校验「实际产出维度 == settings.embedding_dim」→ `models.PointStruct(id=uuid5(document_id), vector, payload=chunk.model_dump(mode="json"))` → `client.upsert`。payload 里存 `content` 原文，RH-20 检索直接能拼上下文，不回查 SQL。
  - `build_index`：编排 ensure_collections → 采集 → 写入，返回统计。
- **幂等**：point id = `uuid.uuid5(NAMESPACE_URL, document_id)`，重复运行同 `document_id` 覆盖而非新增。
- **脚本**：`--reset`（清空重建）、`--skip-personal`、`--dry-run`（只统计切分，不写向量）。

## 4. 设计决策与权衡（面试重点）

- **为什么 Embedding 做成「三后端 + 工厂」而不是只写死一种？**
  - 应对「Embedding 服务不可用」这一风险（PLAN 风险表第一条）。本地 BGE 要装 torch + 下模型（重），OpenAI 兼容 API 要配 key（外发），确定性桩供测试。工厂按 settings 自动选，环境切了不用改代码。
- **为什么 point id 用 `uuid5(document_id)` 而不是自增 id 或随机 UUID？**
  - 自增 id 无法跨进程幂等；随机 UUID 每次生成不同 → 重复构建会堆重复点。`uuid5` 是「同名 → 同 UUID」的确定性哈希，天然幂等，与 RH-17/18 定的 `document_id` 约定一致。
- **为什么维度校验放在「embed 之后」看实际产出，而不是只看配置值？**
  - 配置值可能和真实模型对不上（换了模型但忘改 `EMBEDDING_DIM`）。看 `len(vectors[0])` 是「真话」，能提前拦住维度不匹配，比等 Qdrant 报错更快定位。
- **为什么 payload 里存 `content` 原文？**
  - 检索最终要把命中的文本拼成上下文喂 LLM。存原文让 RH-20 直接 `hit.payload["content"]` 就能拼，不必按 recipe_id 回查 SQLite 重新拼一遍（而且制作记录这类文本 SQLite 里本就不是现成的一句话）。

## 5. 面试高频问题 & 回答要点

**Q1：本地 BGE 和 OpenAI 兼容 API 怎么切换？**
要点：`get_embedding_service()` 按 settings 决策。本地走 sentence-transformers 加载 `EMBEDDING_MODEL`；配了 `OPENAI_API_KEY`+`OPENAI_BASE_URL` 就优先走 `/embeddings`。两者都实现同一个 `EmbeddingService`，上层无感。

**Q2：怎么保证重复跑构建脚本不会越堆越多？**
要点：point id 由 `document_id`（稳定字段+块序号）经 `uuid5` 确定性生成，`upsert` 同 id 即覆盖。清空全量重导用 `--reset` 删 Collection 再重建。

**Q3：个人知识怎么和公共知识分开写？**
要点：两个 Collection 物理隔离——公共菜谱进 `public_recipes`，个人菜谱+制作记录进 `personal_kitchens`（payload 带 `user_id`）。RH-20 检索时个人库必须按 `user_id` 过滤。

**Q4：为什么 embedding 要 `normalize_embeddings=True`？**
要点：BGE 系列通常配合余弦相似度，先 L2 归一化，向量点积就等于余弦相似度，检索更稳定。RH-17 建 Collection 时距离就选了 Cosine，这里对应归一化。

## 6. 踩坑

- **pip 装 sentence-transformers 走不了清华镜像**：本机 `pypi.tuna.tsinghua.edu.cn` 对 `/simple/sentence-transformers/` 返回 403，直接 `pypi.org` 又超时。最终用 `pip install --proxy http://127.0.0.1:7890 sentence-transformers` 走本地代理才通（和 git push 一样走 7890）。**结论：本机装包要带 `--proxy`。**
- **模型下载要走 hf-mirror 或代理**：`huggingface.co` 直连超时，`HF_ENDPOINT=https://hf-mirror.com` 或走 7890 代理都能通。第一次 `SentenceTransformer(...)` 会触发下载，需先设好。
- **`torch` 很重**：sentence-transformers 连带装 torch（CPU 版约数百 MB），这是本地 BGE 的代价；若不想装，改配 OpenAI 兼容 API 即可跳过。
- **单元素 `encode` 的返回形状**：`SentenceTransformer.encode` 传 list 恒返回 2D array，逐个 `.tolist()` 即可；若传裸字符串会返回 1D array，迭代会变成标量。所以统一传 `list[str]`。

## 7. 验证

- 全量测试 65 通过（新增 6 个 index 测试）。
- `--dry-run`（不装模型也能跑）：公共菜谱 189 Chunk、个人知识 1 Chunk。
- **真实向量化（本地 BGE）**：`HF_ENDPOINT=https://hf-mirror.com python scripts/build_vector_index.py` 成功——`public_recipes` 写入 189 点、`personal_kitchens` 写入 1 点，模型 `BAAI/bge-small-zh-v1.5`、维度 512、后端 `LocalBgeEmbedding`。
- **语义检索冒烟**：查「番茄炒蛋怎么做」Top3 = 西葫芦炒鸡蛋 / 炒滑蛋 / 西红柿鸡蛋挂面——全是蛋类菜，且「西红柿鸡蛋挂面」命中印证了 embedding 能捕捉「番茄 ≈ 西红柿」的同义关系（这正是 RH-10 里精确搜索解决不了的缺口，交给 Day 3 向量检索补上）。
