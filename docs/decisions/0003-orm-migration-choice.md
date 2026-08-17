# 0003 — 后端数据层：ORM/迁移工具选型

**状态**：已接受
**日期**：2026-08-17
**关联**：`.claude/rules/data-model.md`、SPEC §4/§6/§11

## 背景

`.claude/rules/data-model.md` 预留了 `backend/**/models/**/*.py`、`backend/**/schemas/**/*.py`、`backend/**/migrations/**/*` 三类路径规则，但具体数据访问方式——手写 `sqlite3` 还是引入 ORM——SPEC 和 AGENTS.md 都没有约定，属于实现层面的开放项。在搭建后端开发环境（虚拟环境、依赖清单）之前需要先拍板，否则依赖清单和目录结构无从下手。

## 权衡

**手写 `sqlite3`（Python 标准库）**：全程手写 SQL 字符串，自己管连接/游标/事务。优点是零额外依赖、执行的 SQL 语义完全可控、不引入抽象层。缺点是每次表结构变更（SPEC §11 里程碑逐步扩表：Demo 只有 `meal_entry`/`daily_summary`/`chat_message`，MVP 起加 `food_favorite`/`exercise_entry`/`body_metric`/`user_profile`/`diet_plan`）都要自己写 `ALTER TABLE` 脚本并保证各环境同步执行，没有版本记录和回滚机制。

**SQLAlchemy（ORM）+ Alembic（迁移）**：表结构定义为 Python 类，`alembic revision --autogenerate` 对比模型和数据库现状自动生成迁移 diff，带版本号可回滚。优点是贴合 SPEC §11 那种"schema 按里程碑分阶段解锁"的演进模式。缺点是多一层抽象——ORM 生成的 SQL 不一定精确等价于手写查询，而这个项目里恰好有几处"铁律"级别的查询语义必须精确：

- `daily_summary` 聚合的 null 传播规则（SPEC §4.2：当天任一营养值为 null，该项汇总也必须是 null，不能当 0 算）
- 结转/补录必须在同一数据库事务内原子完成、且幂等（SPEC §6.1）
- `body_metric` 按字段分别读取"最近一次非空值"（SPEC §4.7），不是简单的按日期排序取最新一行

这几类查询不管用不用 ORM，最终都要精确手写语义，不能假设 ORM 查询构造器或 autogenerate 会自动写对。

## 决策

采用 **SQLAlchemy 2.x（ORM）+ Alembic（迁移）**：

- 表结构演进走 ORM 模型 → `alembic revision --autogenerate` → review diff → `alembic upgrade head` 流程，不手写 `ALTER TABLE`。
- 涉及上述"铁律"级业务查询（结转聚合、null 传播、事务原子性、最近非空值读取）时，允许并要求绕开 ORM 高层查询构造器、直接写原生 SQL（SQLAlchemy 支持在 session/connection 上执行 raw SQL），不迷信自动生成的语义，写完必须对照 SPEC 对应章节逐条验证。
- 迁移脚本目录命名为 `backend/migrations/`（而非 Alembic 默认的 `backend/alembic/`），以匹配 `.claude/rules/data-model.md` 里 `backend/**/migrations/**/*` 的路径规则，确保后续改动这个目录时自动加载对应规则提示。

## 后果

- 依赖清单（`backend/requirements.txt`）新增 `sqlalchemy`、`alembic`。
- 首次定义 ORM 模型（`backend/models/`）时需要接入 `backend/migrations/env.py` 里当前留空的 `target_metadata`，并生成第一条 `alembic revision --autogenerate` 记录初始 schema。
- 定义具体表模型属于业务代码改动，按 CLAUDE.md 约定需要单独进入 plan mode，先读 SPEC §4 对应章节再动，不在本决策/本次环境搭建范围内。
