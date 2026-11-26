# RH-21 基础 RAG Chain

## 1. 一句话总结

把 RH-20 的检索接上 LLM，落地完整 RAG 链路：`问题 → 检索公共+个人 → 相关度过滤 → 构建带来源上下文 → 调用 LLM → 返回回答+引用`，并加一个相关度阈值——检索不到（或命中但低于阈值）时不调 LLM、不伪造来源，暴露 `POST /api/rag/ask`。

## 2. 在项目中的位置

Day 3 的收尾，也是第一个真正调用 LLM 的环节：

- `backend/app/services/rag/llm.py` —— `LLMService` 抽象 + `OpenAICompatLLM` + `get_llm_service()` 工厂。
- `backend/app/services/rag/chain.py` —— `build_context` + `rag_answer`（编排）。
- `backend/app/api/rag.py` —— `POST /api/rag/ask` 接口。
- `backend/app/schemas/rag.py` —— 请求/响应 Schema。
- `backend/tests/test_rag_chain.py` —— 7 个单元测试。

## 3. 实现细节

- **llm.py**：`OpenAICompatLLM.generate(messages)` 用 httpx 直连 `{base_url}/chat/completions`（OpenAI chat 格式，`temperature=0.3`）。`get_llm_service()` 需要 `openai_api_key` + `openai_base_url` + `llm_model` 三者齐备才返回实例，否则返回 `None`。
- **chain.py**：
  - `build_context(chunks)`：拼成 `【来源1】标题（公共菜谱）\n正文...` 的带编号上下文。
  - `rag_answer(...)`：检索 → `score >= MIN_SCORE(0.45)` 过滤 → 空则直接返回「没有找到相关内容」+ 空 sources（**不调 LLM**）→ 否则 `system + 参考资料 + 问题` 喂 LLM → 返回 `RagAskResponse(answer, sources)`。
- **api/rag.py**：`POST /api/rag/ask`。`openid → users.id` 由后端解析（隔离），LLM 未配置时返回 503。
- **system prompt** 明确「只依据资料回答、不要编造、不足则说明、可用【来源N】标注依据」。

## 4. 设计决策与权衡（面试重点）

- **为什么加 `MIN_SCORE=0.45` 相关度阈值，而不是「检索到就喂」？**
  - Qdrant `query_points` 永远返回 top-k，哪怕 query 完全不相关（比如问「量子力学」也给你 6 条菜谱）。不做阈值，无关内容会被喂给 LLM，LLM 可能顺着无关内容编造。实测（BGE-small-zh + 余弦）：相关查询 top1 ≈ 0.55~0.69，无关 ≈ 0.24~0.28，0.45 落在中间。阈值是启发式的，换模型要按新分数分布重调。
- **为什么「检索为空」不调用 LLM？**
  - 这是「不伪造来源」的直接落地。RAG 的价值在于**有依据的回答**；没有依据时宁可直说「没找到」，也不让 LLM 自由发挥编出看似合理、实无出处的答案。这也呼应 PLAN 的约束「所有模型输出都必须经过校验」「检索不到时不会伪造来源」。
- **为什么 LLM 做成可插拔、未配置返回 None？**
  - 和 embedding 一样应对「服务不可用」风险。LLM 是外部依赖（要 key），本地开发可能没有。未配置时 API 返回 503 给出明确指引，而不是启动就崩或运行时抛 500。
- **为什么 `user_id` 由 `openid` 在后端解析，而不是放请求体？**
  - 延续 RH-20 的隔离约定：客户端只带身份凭证（`X-User-Id`），后端解析成内部 `users.id` 再传给检索。用户无法通过改参数读别人的个人知识。

## 5. 面试高频问题 & 回答要点

**Q1：完整 RAG 链路是怎么串起来的？**
要点：`/api/rag/ask` → 解析用户 → 检索公共（`public_recipes`）+ 个人（`personal_kitchens` 按 user_id 过滤）→ 合并去重 → 按 `MIN_SCORE` 过滤 → 拼带编号上下文 → system prompt（只依据资料、不编造）→ LLM chat → 返回回答 + 来源列表。

**Q2：怎么防止 LLM 编造？**
要点：三重防线——① 检索空/低于阈值直接不调 LLM；② system prompt 明确「只依据资料、不足则说明」；③ 返回 sources 让答案可追溯。第一版先做①②，后续可加 RAGAS faithfulness 评测（RH-45）。

**Q3：`temperature` 为什么设低（0.3）？**
要点：RAG 回答要**忠实于检索上下文**，低温度减少随机性、更贴近给定资料。高温度适合创意生成，不适合「有依据的问答」。

## 6. 踩坑

- **`query_points` 永远返回 top-k，不意味着「检索到」**：无关 query 也会拿到结果（分数低）。必须靠分数阈值过滤，否则「检索为空不伪造」这条验收实际上测不出来——因为 `merged` 永远非空。
- **相关度分数是模型相关的**：0.45 是 BGE-small-zh-v1.5 + 余弦的分界值，换 embedding 模型（尤其换维度/距离）要重新采样分布定阈值，不能照搬。
- **未配置 LLM 时不要静默降级**：返回 503 + 明确提示（配哪三个环境变量），比返回一个假的「上下文回显」更诚实，也避免上线后 LLM 静默失效。

## 7. 验证

- 全量测试 76 通过（新增 7 个 chain 测试）。
- 真实 Qdrant + 本地 BGE + mock LLM 冒烟：
  - 「番茄炒蛋怎么做」→ 6 条相关来源，上下文正确喂给 LLM。
  - 「量子力学薛定谔方程推导」→ 命中分数 0.24~0.28，低于阈值，返回「没有找到相关内容」+ 0 来源，**未调 LLM**。
- API：未配置 LLM 时 `POST /api/rag/ask` 返回 503。
