# RH-03 Python 环境与 FastAPI 骨架

## 1. 一句话总结

用 venv 建独立 Python 环境，装上 FastAPI / uvicorn / SQLAlchemy / pydantic，写出第一个「能启动、能健康检查」的后端应用，并把所有配置集中到 `.env`。

## 2. 在项目中的位置

后端的最小可运行骨架。`app/main.py` 里的 `app` 对象是后续所有接口（菜谱 CRUD、推荐、菜单规划……）的挂载点；`app/core/config.py` 是全局唯一的配置入口。

## 3. 实现细节

- **venv**：`python -m venv .venv`，隔离依赖，避免污染 Anaconda 全局环境。
- **requirements.txt**：fastapi、uvicorn、sqlalchemy、pydantic、pydantic-settings、python-dotenv、httpx（测试用）。
- **config.py**：用 pydantic-settings 的 `BaseSettings` 自动把 `.env` 里的键映射成字段，全项目统一 `from app.core.config import settings` 读取。
- **main.py**：`FastAPI(title=..., debug=...)` 创建实例，`@app.get("/health")` 定义健康检查。
- **启动方式**：`cd backend && uvicorn app.main:app --reload`。
- **验证**：`GET /health` 返回 `200` + `{"status": "ok", "app": "RecipeHub"}`（TestClient 和真实 uvicorn 均验证通过）。

## 4. 设计决策与权衡（面试重点）

- **为什么 FastAPI 而不是 Flask？**（上游参考项目正好是 Flask，这是很好的对比点）
  - 原生 async、自动生成 OpenAPI / Swagger 文档、Pydantic 请求校验开箱即用、类型提示友好。
  - Flask 更轻量，但做请求校验和接口文档都要额外加插件，异步支持也不如 FastAPI 原生。
- **为什么用 pydantic-settings 而不是到处 `os.getenv`？** 集中管理、有类型和默认值、启动即校验，避免配置散落各处、变量名拼错要到运行时才暴露。
- **为什么密钥只放 `.env`？** 前端代码和 Git 仓库都可能泄露密钥；密钥必须只在后端环境变量里，前端一律拿不到。
- **为什么用 SQLAlchemy 2.0？** 作为 ORM 管理表关系、防 SQL 注入、后续换库成本低（虽然本项目固定用 SQLite）。
- **为什么 uvicorn？** ASGI 服务器，是 FastAPI 官方推荐的运行方式，支持 async。

## 5. 面试高频问题 & 回答要点

**Q1：FastAPI 和 Flask 的区别？为什么选 FastAPI？**
要点：异步 / 性能、自动接口文档、Pydantic 校验、类型提示。可补一句「上游参考项目用的就是 Flask，我评估后选了 FastAPI，更能支撑后面的 RAG + 异步调用」。

**Q2：ASGI 和 WSGI 是什么？**
要点：WSGI 是同步的 Python Web 服务接口标准（Flask/Django 用）；ASGI 支持异步（FastAPI 用），uvicorn 就是 ASGI 服务器。异步的好处是等模型 API 这种 IO 密集操作时不会阻塞其他请求。

**Q3：pydantic 是干什么的？**
要点：数据校验与序列化，把请求/响应/LLM 输出约束成带类型的结构，非法数据直接拒绝（FastAPI 里返回 422）。这是本项目后面「LLM 输出可靠性」的基石——LLM 输出不可控，靠 Pydantic 兜底。

**Q4：为什么 API Key 不能放前端？**
要点：前端代码可被反编译 / 抓包拿到，泄露即被盗刷；所以密钥只在后端，前端只拿后端签发的 token。

**Q5：`/health` 是干嘛的？**
要点：健康检查，用来确认服务活着，也是监控/负载均衡探活的标准做法；对项目而言是「先让最小链路跑通」的第一步。

## 6. 踩坑

- **Python 3.13 偏新**：后面 Day3 的 torch / sentence-transformers 等 RAG 依赖要确认有 cp313 的 wheel（提前标记的风险）。
- **Windows 上 venv 路径不同**：可执行文件在 `.venv/Scripts/`（Linux 是 `bin/`）。
- **`.env` 加载路径**：config.py 的 `env_file=".env"` 是相对「启动目录」，所以必须在 `backend/` 目录下启动，否则读不到配置。
- **TestClient 弃用警告**：starlette 提示 httpx → httpx2 的 deprecation，无害，可后续处理。
