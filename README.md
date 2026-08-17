# DietApp

单用户减脂追踪 PWA。产品以手机竖屏为主要使用形态，电脑浏览器复用同一套 UI；业务数据由私有后端持久化。

## 项目入口

- 产品需求：[docs/product/PRD.md](docs/product/PRD.md)
- 技术契约：[docs/product/SPEC.md](docs/product/SPEC.md)
- UI 设计：[docs/design/design.md](docs/design/design.md)
- 架构决策记录：[docs/decisions/](docs/decisions/)
- 仓库工作公约：[AGENTS.md](AGENTS.md)

## 目录职责

- `backend/`：FastAPI、业务服务与 SQLite 持久化。
- `frontend/`：React + TypeScript PWA。
- `tests/`：单元、集成与验收测试。
- `docs/`：产品、设计和架构决策真源。

## 快速开始

后端:

```
conda activate vibe-coding
pip install -r backend/requirements-dev.txt
cd backend && alembic upgrade head   # 会改到真实 SQLite,先确认无误再跑
uvicorn app.main:app --reload
```

前端:

```
cd frontend
npm install
cp .env.example .env
npm run dev
```

跑测试:

```
conda activate vibe-coding && pytest      # 后端,仓库根目录跑
cd frontend && npm test                    # 前端
```
