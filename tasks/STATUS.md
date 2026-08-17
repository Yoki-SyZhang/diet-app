# 执行进度表

全局进度表,边做边勾,覆盖更新,不新建计划文件(见 AGENTS.md)。同一 Feature Branch 列出的多个子步骤合并为一个 PR(拆开写是为了任务/验收粒度清楚,不代表要拆成多个 PR)。

---

## Demo 里程碑(PRD §9.1 / SPEC §11.1)— 验证饮食核心闭环

| 步   | 交付什么                                       | 主要碰                                                                                                                                        | 验收绿灯                                                                                           | Feature Branch (PR)                     | 完成 |
| ---- | ---------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- | --------------------------------------- | ---- |
| 1.1  | 后端骨架 + 健康检查                            | FastAPI app factory、config(pydantic-settings)、SQLAlchemy engine/session、Alembic env.py 接入(占位)、健康检查端点                            | `uvicorn` 起服务、`GET /health` 200、`alembic upgrade head` 可跑(占位库)                     | `feature_demo_01_scaffold`            | [ ]  |
| 1.2  | Demo 数据模型 + 首条迁移                       | ORM 定义`meal_entry`/`daily_summary`/`chat_message`/`food_base_cn`/`food_base_us`(SPEC §4.1/4.2/4.4/6.4);首条 `alembic revision` | 迁移建表;单测断言营养素字段可空(不是 0)、无`user_id`、`daily_summary` 字段类型对 null 传播友好 | `feature_demo_01_scaffold`(同 PR)     | [ ]  |
| 1.3  | 前端 PWA 空壳                                  | Vite+React+TS scaffold、manifest+SW 基础配置、记录/看板两个空 Tab、design.md 色板/字体 token 基础层                                           | `npm run dev` 两 tab 可切换渲染;build 产物可安装到手机主屏(粗验,完整验收留 1.14)                 | `feature_demo_01_scaffold`(同 PR)     | [ ]  |
| 1.4  | `food_base_cn` 导入                          | 固定 commit 快照导入脚本(见`docs/data/food_base-import-log.md`)、可食率/`Tr`/破折号/空值处理、校验报告                                    | 单测覆盖可食率口径、OCR 脏值不转 0、重复编码检测;对当前快照跑出预期记录数(1657 条)                 | `feature_demo_02_food_base`           | [ ]  |
| 1.5  | `food_base_us` USDA 适配器                   | USDA client + 按 nutrientID+name+unit 取值适配器、`fdcId` 缓存(SPEC §4.4.2)                                                                | 单测用录制的 USDA 响应 fixture 验证按 ID 取值(非数组位置)、缺失 null、能量口径不相加               | `feature_demo_02_food_base`(同 PR)    | [ ]  |
| 1.6  | 单位归一 + 营养计算引擎                        | g 归一、每 100g×克重/100、可食率仅在"总重"输入时应用、null 传播、`source_tag` 赋值(SPEC §7.1/7.3/7.8)                                     | 单测覆盖生/熟口径匹配、缺失不当 0、可食率触发条件                                                  | `feature_demo_03_query_engine`        | [ ]  |
| 1.7  | 四级查询 ②③(中国库→USDA)                    | 逐级召回、单候选直采、无候选降级、"兼容"判定(名称语义+`preparation_state`+unit)、§7.2 LLM 候选消歧(真实调用,ADR 0001 `qwen-plus` 路由)   | 集成测试:逐级召回、单候选直采、多候选交 LLM、无明确常见项转用户选择                                | `feature_demo_03_query_engine`(同 PR) | [ ]  |
| 1.8  | 四级查询 ④(LLM 拆解 + 网络搜索兜底)           | ADR 0002 拆解机制(SPEC §7.9)+ ADR 0004 博查`web_search` 接入、三工具调用循环、单项估算兜底 `source_tag=decompose_estimate`                     | 整菜拆解→组成项重新过 ②③ 级→后端加总;单项查不到时退回估算且不阻断同菜其他项                    | `feature_demo_04_decompose_fallback`  | [ ]  |
| 1.9  | LLM 自然语言解析(§8.1)                        | 供应商无关适配层接百炼、`qwen-plus` 路由(ADR 0001)、食物名/数量/单位/`preparation_state`/餐次提取、`clarify` 追问                       | 契约测试:合法结构率 ≥95%、信息不足触发`clarify`、不生成候选之外食物                             | `feature_demo_05_text_parsing`        | [ ]  |
| 1.10 | 手动录入路径(§7.5 C)                          | 结构化表单 API,绕过 LLM 解析但走同一四级查询;未解析不写入                                                                                     | 集成测试:查到→写入;查不到→不写入 + 正确提示(LLM 可用转追问/不可用明确提示)                       | `feature_demo_06_write_path`          | [ ]  |
| 1.11 | 写入 + 只读今日明细(§7.4 确认矩阵打通)        | 直接写入/歧义确认预览两条路径的持久化层、`chat_message` 写入、今日明细只读查询 API                                                          | 端到端:文本→解析→查询→计算→(视情况确认)→写入→明细查询刷新正确                                | `feature_demo_06_write_path`(同 PR)   | [ ]  |
| 1.12 | 对话补录/修正(仅当天,§6.2+§8.3)              | 当天 add/update/delete 操作草案生成、预览、Confirm 后同事务原子执行                                                                           | 集成测试:预览与执行结果一致、同事务内增删改正确                                                    | `feature_demo_07_dialogue_amend`      | [ ]  |
| 1.13 | 结转任务 + A1 趋势图(前后端打通,§6.1+看板 A1) | 02:00 结转 job(APScheduler)、启动补跑、7 天清理边界(含`chat_message`)、幂等、A1 趋势 API + 前端柱状图                                       | 结转重复触发不重复累加;补跑覆盖"漏跑后重启";短期/长期库抽样一致;A1 图正确渲染                      | `feature_demo_08_carryover_trend`     | [ ]  |
| 1.14 | 记录页前端 + PWA 打磨 + Demo 验收清单          | 对话输入组件 + 手动录入表单 + 今日明细只读 UI 接通后端;断网提示;跑 SPEC §11.1 技术验收                                                       | SPEC §11.1 全部验收项过;PRD §9.1 阶段完成标志达成                                                | `feature_demo_09_record_page_pwa`     | [ ]  |

**依赖顺序**:01 → 02 → 03 → (04、05 可并行) → 06 → 07 → 08 → 09。04/05 都不改
03 已合入的查询引擎内部实现,可以并行开分支,谁先 ready 谁先合、另一个 rebase。
其余基本是强依赖链,按顺序做。

---

## 后续里程碑(未拆解,待 Demo 完成后再拆)

- **9.2 MVP** — 三大业务模块形成日常闭环(照片录入、常吃库、运动、身体数据、BMR、减脂计划、今日明细可编辑、7 天补录)
- **9.3 Closed Beta** — 对话入口扩展到全场景(运动/身体数据对话解析接入统一入口)
- **9.4 Release Candidate** — 私有 PWA 稳定性(安装/更新/备份恢复/私有访问)
- **9.5 Stable** — 个人正式版与长期维护
