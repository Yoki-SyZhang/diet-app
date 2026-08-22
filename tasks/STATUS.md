# 执行进度表

全局进度表,边做边勾,覆盖更新,不新建计划文件(见 AGENTS.md)。同一 Feature Branch 列出的多个子步骤合并为一个 PR(拆开写是为了任务/验收粒度清楚,不代表要拆成多个 PR)。

**测试文件命名约定**:后端 `test_demo_<NN>_<关键词>.py`、前端 `demo_<NN>_<关键词>.test.tsx`;`NN` 取所属 Feature Branch 名里的两位数字(`feature_demo_01_scaffold`→01……`feature_demo_08_pwa_polish`→08),不是"步"列的小数位——同一 PR 下多个步骤各自的测试文件 `NN` 相同,靠关键词区分。`conftest.py` 不改名。

**完成时间记录约定**:勾选"完成"列时格式为 `[x] YYYY-MM-DD HH:MM CDT/CST`,精确到分钟,统一用美国中部时区(夏令时 CDT / 标准时 CST)。

---

## Demo 里程碑(PRD §9.1 / SPEC §11.1)— 验证饮食核心闭环

| 步   | 交付什么                                       | 主要碰                                                                                                                                        | 验收绿灯                                                                                           | 测试文件与内容 | Feature Branch (PR)                     | 完成 |
| ---- | ----------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- | ---- | --------------------------------------- | ---- |
| 1.1  | 后端骨架 + 健康检查                            | FastAPI app factory、config(pydantic-settings)、SQLAlchemy engine/session、Alembic env.py 接入(占位)、健康检查端点                            | `uvicorn` 起服务、`GET /health` 200、`alembic upgrade head` 可跑(占位库)                     | `tests/backend/test_demo_01_health.py`——GET /health 返回 200 且 db 连通;数据库异常返回 503 | `feature_demo_01_scaffold`            | [x] 2026-08-17 16:02 CDT  |
| 1.2  | Demo 数据模型 + 首条迁移                       | ORM 定义`meal_entry`/`daily_summary`/`chat_message`/`food_base_cn`/`food_base_us`(SPEC §4.1/4.2/4.4/6.4);首条 `alembic revision` | 迁移建表;单测断言营养素字段可空(不是 0)、无`user_id`、`daily_summary` 字段类型对 null 传播友好 | `tests/backend/test_demo_01_schema.py`——5 张表结构、字段可空性、无 user_id、CHECK 约束校验 | `feature_demo_01_scaffold`(同 PR)     | [x] 2026-08-17 16:02 CDT  |
| 1.3  | 前端 PWA 空壳                                  | Vite+React+TS scaffold、manifest+SW 基础配置、记录/看板两个空 Tab、design.md 色板/字体 token 基础层                                           | `npm run dev` 两 tab 可切换渲染;build 产物可安装到手机主屏(粗验,完整验收留 1.14)                 | `frontend/src/tests/demo_01_app.test.tsx`——两个 tab 渲染 + 点击切换;健康检查文案渲染出现 | `feature_demo_01_scaffold`(同 PR)     | [x] 2026-08-17 16:02 CDT  |
| 1.4  | `food_base_cn` 导入                          | 固定 commit 快照导入脚本(见`docs/data/food_base-import-log.md`)、可食率/`Tr`/破折号/空值处理、校验报告                                    | 单测覆盖可食率口径、OCR 脏值不转 0、重复编码检测;对当前快照跑出预期记录数:解析 1657 条,排除 1 条`192011`麻子籽全字段缺失记录,插入 1656 条                 | `tests/backend/test_demo_02_food_base_cn_import.py`——`coerce_nutrient_value`/`parse_record`/去重/全空过滤/插入;`test_demo_02_food_base_cn_import_real_snapshot.py`——真实 61 文件精确 1656 条 + 脏值分布;`test_demo_02_import_cli.py`——`run_import` 全部防护措施(dry-run 不连库、真实库路径判定、空快照拒绝、重复导入拒绝、replace 回滚、数据异常拒绝) | `feature_demo_02_food_base`           | [x] 2026-08-20 23:56 CDT  |
| 1.5  | `food_base_us` 快照导入                      | USDA 官方批量下载(Foundation+Survey)快照导入脚本 + 按 id+name+unit 取值适配器(SPEC §4.4.2,选型依据见 ADR 0005),和 1.4 对称的整表覆盖式导入,不是运行时缓存 | 单测用从真实下载文件截取的 fixture 验证按 id+name+unit 取值(非数组位置)、缺失 null、能量口径不相加;对当前快照跑出预期记录数(363+5432=5795 条,0 处跨数据集 fdc_id 冲突) | `tests/backend/test_demo_02_usda_adapter.py`——真实截取+人工构造 fixture 验证 id+name+unit 三重匹配、能量多候选优先级、0 值保留;`test_demo_02_food_base_us_import.py`——跳过 null、missing_nutrient_counts、跨文件冲突检测、插入;`test_demo_02_food_base_us_import_real_snapshot.py`——真实 5795 条精确验收;`test_demo_02_us_import_cli.py`——`run_import` 全部防护措施(含 fdc_id 冲突永远硬失败) | `feature_demo_02_food_base`(同 PR)    | [x] 2026-08-20 23:56 CDT  |
| 1.6  | 单位归一 + 营养计算引擎                        | g 归一、每 100g×克重/100、null 传播、`source_tag` 赋值(SPEC §7.1/7.3/7.8);可食率(总重→可食部)转换绑定在 `food_base_cn` 查询链路上,随四级查询链一起留到 Closed Beta,Demo 阶段不实现,详见 `tasks/current.md`                                     | 单测覆盖克重营养换算、null 传播、0/负数/非有限值拒绝;契约测试确认生熟状态正确传入营养估算(生熟本身由 1.8 解析、1.7 消费,1.6 只做换算)                                                  | —(待实现,NN=03) | `feature_demo_03_query_engine`        | [ ]  |
| 1.7  | 食物营养查询:LLM 直接估算(临时,接口预留后续替换四级查询链) | LLM 按食物名+生熟状态直接产出 per-100g 五项营养值+置信度(SPEC §7.2 里程碑说明),`source_tag=llm_estimate`,产出 §7.4"LLM 直接估算"确认预览(标注"可能不准");真正的 Confirm 写入在 1.9 做,本步不接 DB | 确认预览正确标记必须 Confirm、显示"可能不准"、不含 date/created_at,本阶段不发生数据库写入;`source_tag`/置信度标注正确、缺失营养素为 null 不为 0(kcal 除外,需非空才算可信结果,见 `tasks/current.md`)。"点击 Confirm 后是否写入、部分成功如何处理"放在 1.9 验收 | —(待实现,NN=03) | `feature_demo_03_query_engine`(同 PR) | [ ]  |
| 1.8  | LLM 自然语言解析(§8.1)                        | 供应商无关适配层接百炼、`qwen-plus` 路由(ADR 0001)、食物名/数量/单位/`preparation_state`/餐次提取、`clarify` 追问                       | 契约测试:合法结构率 ≥95%、信息不足触发`clarify`                                                  | —(待实现,NN=03) | `feature_demo_03_query_engine`(同 PR) | [ ]  |
| 1.9  | 写入 + 今日明细 UI(新增 + 手动删除,前后端打通) | 直接写入路径的持久化层、`chat_message` 写入、今日明细查询 API;**前端对话输入组件**(文本框+发送+消息展示)和**今日明细列表 UI**(含手动删除按钮)接通后端 | 端到端:浏览器里输入文本→解析→LLM 估算→Confirm→写入→今日明细列表实时刷新;点击删除按钮正确移除记录且不影响其他行 | —(待实现,NN=04) | `feature_demo_04_write_path`          | [ ]  |
| 1.10 | 结转任务 + A1 趋势图(前后端打通,含图表 UI)    | 02:00 结转 job(APScheduler)、启动补跑、7 天清理边界(含`chat_message`)、幂等、A1 趋势 API + **前端 ECharts 柱状图组件**(此步仅摄入,运动消耗叠加见 1.12) | 结转重复触发不重复累加;补跑覆盖"漏跑后重启";短期/长期库抽样一致;浏览器里 A1 图正确渲染热量柱状图    | —(待实现,NN=05) | `feature_demo_05_carryover_trend`     | [ ]  |
| 1.11 | 身体数据基础录入 UI + BMR                      | `user_profile`/`body_metric` 表、§5.1 BMR 双公式计算引擎;**"我的" Tab 基础信息+身体维度表单 UI**(不含握拳尺寸)接通后端                | 单测覆盖 BMR 双公式切换逻辑(体脂率优先开关)、身体维度按日期取最近非空值;浏览器里表单提交后 BMR 正确显示并重算 | —(待实现,NN=06) | `feature_demo_06_body_metrics`        | [ ]  |
| 1.12 | 运动手动录入 UI + A1 趋势图运动消耗叠加        | `exercise_entry` 表、**看板运动录入表单 UI**(类型/时长/消耗 kcal)接通后端、**A1 图表灰色遮盖逻辑前端渲染**(依赖 1.11 的 BMR 才能算出每日 Δ,§3.2/SPEC §2.2 A1) | 集成测试:运动记录写入正确;浏览器里 A1 图运动消耗遮盖高度和柱顶等效摄入符合 `min(activity,total)`/`max(total-activity,0)` 公式 | —(待实现,NN=07) | `feature_demo_07_exercise_trend_overlay` | [ ]  |
| 1.13 | PWA 打磨 + Demo 验收清单                       | manifest/SW 完整配置、断网提示、加载态;逐项跑 SPEC §11.1 技术验收(核对 1.9-1.12 已交付的 UI)                                          | SPEC §11.1 全部验收项过;PRD §9.1 阶段完成标志达成;PWA 可安装到手机主屏幕并独立启动               | —(待实现,NN=08) | `feature_demo_08_pwa_polish`          | [ ]  |

**依赖顺序**:01 → 02 → 03 → 04 → 05 → 06 → 07 → 08,强依赖链,按顺序做。1.6-1.8 合并为一个 PR(同一份"食物营养查询引擎"能力,不含 UI,后端契约测试即可验收);**1.9 起每一步都要求把对应 UI 接通后端**,不再留到最后统一做前端。
06(身体数据)本身不依赖 04/05 的食物查询/写入链路,可以在 03 完成后提前并行开工;
但 07(运动+A1 叠加)同时依赖 05(A1 图表)和 06(BMR),需等两者都合入后再做。

---

## 后续里程碑(未拆解,待 Demo 完成后再拆)

- **9.2 MVP** — 在 Demo 已有的运动/身体数据/BMR 基础上,补齐照片录入、常吃库、减脂计划、今日明细改数量、7 天对话补录
- **9.3 Closed Beta** — 对话入口扩展到全场景(运动/身体数据对话解析接入统一入口)
- **9.4 Release Candidate** — 私有 PWA 稳定性(安装/更新/备份恢复/私有访问)
- **9.5 Stable** — 个人正式版与长期维护
