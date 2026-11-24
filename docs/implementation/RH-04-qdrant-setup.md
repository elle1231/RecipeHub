# RH-04 接入 Qdrant 向量数据库

## 1. 一句话总结

用 docker-compose 拉起本地 Qdrant 服务，装上 `qdrant-client`，写一个「只拿连接」的 `app/db/qdrant.py`，把连接信息集中到 `.env`，为后面双知识库（RH-17 建 Collection、RH-19 写向量、RH-20 检索）打好地基。

## 2. 在项目中的位置

这是 RAG 基础设施的第一块「地基」。后续所有语义检索都从这里拿连接：

- `docker-compose.yml` —— 定义 Qdrant 服务、端口、持久化卷，一条命令起/停。
- `backend/app/db/qdrant.py` —— `get_qdrant_client()` 返回连接客户端，业务逻辑不在这里。
- `backend/app/core/config.py` —— 新增 `qdrant_host` / `qdrant_port` 配置项。
- `backend/requirements.txt` —— 新增 `qdrant-client` 依赖。
- `.env` / `.env.example` —— 新增 `QDRANT_HOST` / `QDRANT_PORT`。

## 3. 实现细节

- **docker-compose.yml**：`qdrant/qdrant:latest`，映射 6333（HTTP/REST）和 6334（gRPC），挂 `qdrant_storage:/qdrant/storage` 持久化，`restart: unless-stopped`。
  - 启动：`docker compose up -d`；停止：`docker compose down`；重置（清数据）：`docker compose down -v`。
- **get_qdrant_client()**：`QdrantClient(host=..., port=...)`。构造时**不会**立刻建立连接，真正的连接发生在调用它的方法（如 `get_collections()`）时，所以这里只做「惰性拿到客户端」，不做任何网络操作。
- **config.py**：沿用 `BaseSettings` 自动映射 `QDRANT_HOST` / `QDRANT_PORT`，默认 `localhost:6333`。
- **验证方式**：`docker compose up -d` 后，用 `client.get_collections()` 确认能连上；或直接 `curl http://localhost:6333/healthz` 看服务是否存活。

## 4. 设计决策与权衡（面试重点）

- **为什么选 Qdrant 而不是 FAISS / Chroma / Milvus？**
  - Qdrant 是独立服务（Docker 一键起），自带 HTTP/gRPC API 和可视化 dashboard（6333 端口）；FAISS 只是本地库，没有独立服务形态。
  - 原生支持 **Payload 过滤**——这是本项目「个人知识库按 `user_id` 隔离」的关键能力，后面 RH-20 检索时要靠 `user_id` 过滤个人知识。
  - 相比 Milvus 更轻量、部署简单，本地 MVP 完全够用。
- **为什么 SQLite 存结构化、Qdrant 存向量，双存储并存？**
  - 菜谱的食材用量、步骤、权限、发布状态这类精确字段必须用 SQL（精确查询、事务、权限最终依据）；
  - 向量库只负责「语义相似」检索（如「找一道高蛋白少油的晚餐」），两者职责不同、互补。
- **为什么 `get_qdrant_client()` 只返回连接、不写业务？**
  - 关注点分离：连接是横切基础设施（`db/`），检索/写入逻辑放 `services/rag/`（对应 RH-17/19/20）。这也是 RH-02 定的「api → services → db」依赖方向。
- **为什么用 docker-compose 而不是手动跑进程？**
  - 可复现：换一台机器 `docker compose up -d` 就能起同样的环境；volume 保证重启不丢数据；配置（端口、卷）都写在文件里，不用记命令。

## 5. 面试高频问题 & 回答要点

**Q1：Qdrant 是干嘛的？为什么需要它？**
要点：向量数据库，存储 embedding 并做 ANN（近似最近邻）相似度检索。传统 SQL `LIKE` 只能关键词精确匹配，理解不了「清淡低脂」≈「少油少盐」这种语义；向量检索能按语义召回相关菜谱/经验。

**Q2：Payload 是什么？**
要点：附加在向量点上的结构化元数据（如 `user_id`、`recipe_id`、`visibility`、`version`），可以在检索时做过滤。本项目用它做个人知识库的 `user_id` 隔离，但**权限的最终校验仍在 SQL / 后端**，Payload 只作辅助过滤（防越权是 Day3/Day7 的重点）。

**Q3：向量维度、距离度量怎么定？**
要点：由 embedding 模型决定，不能拍脑袋。本项目用 `BAAI/bge-small-zh-v1.5`（512 维），距离用余弦相似度（Cosine）。这些在 RH-17 建 Collection 时定死，之后换模型会维度不兼容，要重建 Collection。

**Q4：为什么构造 QdrantClient 不立刻报连接错误？**
要点：它是惰性的——构造只是保存 host/port 参数，真正建连在第一次调用方法时。好处是模块可安全 import 和做单元测试；代价是连接问题要等到实际调用才暴露，所以 RH-04 的验收就是「起服务 + 真实调用一次 `get_collections()`」。

## 6. 踩坑

- **Windows 上 Docker daemon 没起**：`docker` 命令报 `npipe:////./pipe/docker_engine ... not found`。需要先启动 Docker Desktop，等 daemon 就绪（`docker info` 成功）后再 `docker compose up`。
- **Docker Desktop 装在非默认路径**（本机在 `D:\Docker`），找可执行文件别死记 `C:\Program Files\Docker`。
- **`QdrantClient` 惰性连接**：import 成功不代表服务连得上，验收一定要真实调用一次方法确认。
- **端口占用**：6333/6334 被别的服务占用时会起不来，`docker compose up` 看报错即可定位。
