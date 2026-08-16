<!-- AGENTS.md — 仓库工作公约。改动前想想:这条是不是"每个 session 都该记住"?
     如果是某一块代码的细节,移到 .claude/rules/ 或 skill,别塞这里。目标 <200 行。 -->

# DietApp — 单用户减脂追踪 PWA

单用户私有后端,不做多人/公开注册。前端 React+TS PWA,后端 Python+FastAPI,
存储单文件 SQLite。产品形态:手机竖屏 PWA,电脑浏览器复用同一 UI,不做原生 App。

## 真源在哪(先读这些,不要凭记忆)

- 产品需求 → `docs/product/PRD.md`
- 技术契约(数据模型/流程/LLM 契约)→ `docs/product/SPEC.md`  ← 业务问题以此为唯一定义
- 版本范围 → PRD §9(权威);技术验收 → SPEC §11(从 §9 派生)
- 前端设计规范 → `docs/design/design.md`
- 当前执行进度 → `tasks/STATUS.md`
- 某个决策"为什么这么定" → `docs/decisions/`

## 铁律(最容易被搞错的,违反=返工)

- 归属日 = date(本地时间 − 2h);时间戳一律 UTC-0 存储。见 SPEC §6.1。
- 食物查询/录入/维护**唯一定义在 SPEC §7**,四级链顺序不可改,LLM 不得生成营养值。
- 单用户:业务表**不加 `user_id`**,不引入账号/用户切换。
- 缺失营养素用 `null`,**绝不用 0 顶替**(区分"未提供"和"确定为零")。
- BMR 双公式切换逻辑见 SPEC §5.1,不要自己简化。
- 未拿到可信营养结果前,**不写 `meal_entry`、不建草稿**(SPEC §7.6)。

## 目录布局

- `backend/` — Python + FastAPI 服务端(骨架待填充);内部预期分出 `models/` `schemas/` `migrations/`,见 `.claude/rules/data-model.md`
- `frontend/` — React + TS PWA(骨架待填充);手机竖屏为唯一正式布局
- `tests/` — 后端/前端测试(骨架待填充, 预期分出验收/单元/集成)
- `tasks/` — `STATUS.md` 当前执行进度, 边做边勾, 覆盖更新, 不新建计划文件, 但每次提交进 git
- `docs/product/` — `PRD.md` 产品需求、`SPEC.md` 技术契约(业务定义唯一真源)；(会变,git 管版本)
- `docs/design/` — `design.md` 前端设计规范、`ui-bundle/` 设计稿静态文件
- `docs/decisions/` — 关键决策记录("为什么这么定")
- `.claude/rules/` — 按路径自动加载的分区细则:`backend.md` `frontend.md` `data-model.md`

## 命令

- 后端起服务:`...`
- 跑测试:`...`   ← done 的判定
- 前端 dev:`...`
- lint:`...`

## Definition of Done

- 相关单元/集成测试全绿(贴命令+输出,不接受"它能跑")。
- 一个小步 = 一个 feature branch → 一个 PR。PR 描述写清对应 PRD §9 哪部分 + 验收证据。

## Git 工作流

- `main` 永远可运行、测试永远绿;所有改动走 feature branch + PR 合入。
- 开工前先 `git rebase main`;小步提交,方便回退。
- 碰共享地基(SPEC §4/§5/§7)要单独开分支先合,再通知其他分支 rebase。

## 需要我(人)确认才能做的

- 任何触碰真实 SQLite、跑数据库迁移、删除数据的动作。
- 改动 7 天清理边界 / 结转逻辑后作用于真实数据。
- push 到 main、改 `.claude/settings.json` 权限。
