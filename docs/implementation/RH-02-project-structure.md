# RH-02 初始化仓库结构与 Git 管理

## 1. 一句话总结

建立 `backend/`（后端）、`miniprogram/`（小程序）、`scripts/`（脚本）、`docs/`（文档）四层目录，并完成 git 初始化与 `.gitignore`，让项目从第一天就有清晰、可扩展的骨架。

## 2. 在项目中的位置

这是「地基」。后续每一个 RH 产出的代码都会落到这些目录里——数据库模型进 `backend/app/models/`，接口进 `backend/app/api/`，业务逻辑进 `backend/app/services/`。目录定下来，后面 40 多个 Issue 才有地方放，别人（或未来的你）才知道去哪里找代码。

## 3. 实现细节

目录结构及其职责：

```
recipehub/
├── backend/
│   ├── app/
│   │   ├── api/          # 接口层：只做参数接收/响应，不写业务
│   │   ├── core/         # 配置、安全等横切关注点
│   │   ├── db/           # 数据库连接、session 管理
│   │   ├── models/       # SQLAlchemy 表模型
│   │   ├── schemas/      # Pydantic 请求/响应模型
│   │   └── services/     # 业务逻辑，按 recipe/rag/recommendation/menu 四模块分
│   ├── data/             # 本地数据文件
│   ├── uploads/          # 上传图片
│   ├── tests/            # 后端测试
│   ├── requirements.txt
│   └── .env.example
├── miniprogram/
│   ├── pages/            # 页面（home/kitchen/recipe-library/recommendation/menu-planner/profile）
│   ├── components/       # 复用组件
│   ├── utils/            # 请求封装等工具
│   ├── app.js / app.json / app.wxss
├── scripts/              # 数据导入、向量索引等一次性脚本
├── docs/                 # PRD、Plan、implementation 文档
└── README.md
```

关键点：`.gitignore` 忽略 `.env`、`uploads/`、`*.db`、`node_modules/`、`__pycache__/` 等；而 `.env.example` 必须提交。

## 4. 设计决策与权衡（面试重点）

- **为什么前后端分离？** 小程序（前端）不能也不应该直接连 SQLite/Qdrant/模型 API——密钥会暴露，也没法做统一的权限校验。所以所有数据访问都收敛到 FastAPI，小程序只通过 `wx.request` 调后端 API。
- **为什么 backend 内分 api/core/db/models/schemas/services 六层？** 关注点分离 + 依赖方向单一：`api → services → models/db`。避免「一层写所有东西」的大泥球，也让每层可以独立测试、独立替换。
- **为什么 services 再按业务拆 recipe/rag/recommendation/menu？** 正好对应 PRD 四大核心模块，一个模块的改动不牵连其他模块。

## 5. 面试高频问题 & 回答要点

**Q1：你的项目目录是怎么组织的？为什么这么分？**
要点：按「前后端分离 + 后端再分层（api/models/schemas/services）」讲，强调「业务逻辑收敛在 service，接口层不写业务」。

**Q2：`.env` 和 `.env.example` 有什么区别？**
要点：`.env` 存真实密钥、进 gitignore 不提交；`.env.example` 是模板（只有字段名和示例值），要提交，方便别人照着填一份自己的 `.env`。

**Q3：为什么忽略 `*.db`、`uploads/`？**
要点：这些是运行时产物 / 用户数据，不该进版本库；换一台机器应该能靠脚本重新生成，而不是靠 git 同步一堆大文件。

## 6. 踩坑

- **git 不追踪空目录**：所以空目录里放 `.gitkeep` 占位。
- **Windows 换行 LF→CRLF 警告**：无害，但团队协作建议统一换行风格（可配 `.gitattributes`）。
- **GitHub 仓库名大小写**：`RecipeHub` vs `Recipehub` 会触发 remote 的「This repository moved」提示，统一成一致的大小写即可。
