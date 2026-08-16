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

当前仅完成文档与仓库脚手架，运行和验证命令将在代码骨架确定后补充。
