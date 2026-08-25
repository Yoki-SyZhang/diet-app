# DietApp

单用户减脂追踪 PWA。产品以手机竖屏为主要使用形态，电脑浏览器复用同一套 UI；业务数据由私有后端持久化。

### 当前状态：MVP Demo 开发中

已完成自然语言录入、食物识别与估算、用户确认/修改及写入记录的核心闭环。最新开发进度见 `feature_demo_04_write_path`。正在做 AI 指标验收，全部达标后再转正式 PR。

## 项目入口

- 后端应用入口：[`backend/app/main.py`](backend/app/main.py)，本地 API 默认运行在 `http://localhost:8000`。
- 前端应用入口：[`frontend/src/main.tsx`](frontend/src/main.tsx)，页面根组件为 [`frontend/src/App.tsx`](frontend/src/App.tsx)，本地页面默认运行在 `http://localhost:5173`。
- 产品需求真源：[`docs/product/PRD.md`](docs/product/PRD.md)。
- 数据模型、业务流程和接口契约真源：[`docs/product/SPEC.md`](docs/product/SPEC.md)。
- 前端设计规范：[`docs/design/design.md`](docs/design/design.md)。
- 全局进度与当前计划：[`tasks/STATUS.md`](tasks/STATUS.md)、[`tasks/current.md`](tasks/current.md)。
- 架构决策记录：[`docs/decisions/`](docs/decisions/)。
- 仓库工作公约：[`AGENTS.md`](AGENTS.md)。

## 目录职责

- `backend/app/`：FastAPI 应用、配置、数据库会话、ORM 模型、Schema 和 API 路由。
- `backend/migrations/`：Alembic 数据库迁移；运行迁移会修改 SQLite，操作真实数据库前先确认。
- `backend/data/`：本地 SQLite 数据文件，不提交 Git。
- `frontend/src/`：React + TypeScript PWA 源码、样式和前端测试。
- `frontend/public/`：PWA 图标等无需经过源码转换的静态资源。
- `tests/backend/`：后端单元、集成与验收测试；前端测试放在 `frontend/src/tests/`。
- `docs/product/`：PRD 与 SPEC；业务定义以这里为准。
- `docs/design/`：前端设计规范和设计稿资源。
- `docs/decisions/`：关键技术与产品决策的背景和理由。
- `tasks/`：`STATUS.md` 记录全局进度，`current.md` 记录当前步骤的细粒度计划。

## 快速开始

以下命令以 PowerShell 为例。后端和前端需要分别占用一个终端窗口。

### 1. 启动后端

```powershell
conda activate vibe-coding
pip install -r backend/requirements-dev.txt
cd backend

# 仅首次初始化或迁移版本变化时执行；会修改真实 SQLite，先确认无误
alembic upgrade head

uvicorn app.main:app --reload
```

启动后可访问健康检查：[http://localhost:8000/health](http://localhost:8000/health)。

### 2. 启动前端

在新的 PowerShell 窗口中，从仓库根目录运行：

```powershell
cd frontend
npm install

# 首次启动时复制本地配置；已有 .env 时跳过，避免覆盖自定义后端地址
Copy-Item .env.example .env

npm run dev
```

浏览器打开 [http://localhost:5173](http://localhost:5173)。前端通过 `frontend/.env` 中的`VITE_API_BASE_URL` 访问后端；默认值为 `http://localhost:8000`。
