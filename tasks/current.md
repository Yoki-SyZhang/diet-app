# feature_demo_01_scaffold — 实现计划(Demo 1.1–1.3)

## Context

Demo 里程碑已在 `tasks/STATUS.md` 拆成 14 个子步骤、9 个 PR。这是第一个 PR:
1.1 后端骨架+健康检查、1.2 Demo 数据模型+首条迁移、1.3 前端 PWA 空壳,三步合并成一个
分支 `feature_demo_01_scaffold`。三者都是"地基"性质的脚手架工作(无业务逻辑分支需要
挑选、无外部数据源要接),合并评审比拆三个 PR 更省流程开销。

范围严格锁定在这三步:不碰 food_base_cn/us 的真实导入(1.4/1.5)、不碰四级查询
(1.6-1.8)、不碰 LLM 契约(1.9)、不碰写入路径(1.10-1.11)。本 PR 交付的是能跑起来的
空壳 + 建好的表结构,不含任何这些表的真实业务数据写入逻辑。

依据:`docs/product/SPEC.md` §4.1/4.2/4.4/6.1/6.4/11.1、`docs/product/PRD.md` §9.1、
`docs/decisions/0003-orm-migration-choice.md`(SQLAlchemy+Alembic 选型,已拍板不重议)、
`docs/design/design.md`(色板/字体 token)、`.claude/rules/{backend,frontend,data-model}.md`、
已核实的仓库现状(`backend/` 只有 `.env`/`alembic.ini`/`migrations/env.py`/`requirements*.txt`/
空的 `data/dietapp.db`;`frontend/` 只有 `.gitkeep`;conda `vibe-coding` 环境已装好全部
Python 依赖;Node v25.9.0/npm 11.12.1 可用)。

**评审后确定的两处 SPEC 字面量修订**(你在计划评审时提出,已决定在本分支里一并做):

1. `meal_entry.meal_slot` 的第四档从 `snack` 改成 `other`(注意 `food_favorite.category`
   里也有个 `snack`,那个是"零食"这个食物分类,和这里"加餐"这个餐次概念完全不是一回事,
   **不动**,而且 `food_favorite` 本来就是 MVP 才建的表,本 PR 也碰不到)。
2. `source_tag` 里第④级(拆解兜底)对应的取值从 `web_estimate` 改成 `decompose_estimate`,
   更准确地反映"这是第④级拆解出来的估算",而不是字面上的"网络搜索出来的"。

这两个都是 `docs/product/SPEC.md` §4.1/§4.5/§7.8/§8.5 里写死的字面量,不只是实现细节
命名,所以按你的决定,在本分支里一并同步修订 SPEC.md 原文(逐处见下方"SPEC.md 同步"一节),
保持"SPEC 是唯一业务定义"这条不漂移。`docs/decisions/0002-composed-dish-fallback.md` 这份
ADR 里也提到旧值 `web_estimate`,但 ADR 是"当时为什么这么决定"的历史记录,不做事后编辑,
不touch;`tasks/STATUS.md` 1.8 行里的提法一并顺手改掉,那是我自己的进度表,不是历史记录。

**关于"落到真实 backend/data/dietapp.db 前要不要停下来确认"**:这道关卡是照抄 AGENTS.md
里"任何触碰真实 SQLite、跑数据库迁移的动作需要人确认"这条铁律。你已经在计划评审阶段确认
过"这次跳过,直接执行"——因为文件当前确实是 0 字节空文件,没有真实数据可丢,而且这个决定
本身就是通过这轮计划确认做出的,不需要再执行到那一步时二次打断。**所以本计划执行到 1.2 的
迁移步骤时会直接对 `backend/data/dietapp.db` 跑 `alembic upgrade head`,不会再停下来问。**

---

## 目标目录结构(本 PR 新增/修改)

```
backend/
  app/
    __init__.py               
    main.py                     # create_app() 工厂 + 模块级 app,供 `uvicorn app.main:app` 启动用
    config.py                   # pydantic-settings Settings:从 .env 读 DATABASE_URL、CORS 白名单等配置
    db.py                       # SQLAlchemy engine / SessionLocal / get_db() 可覆盖依赖函数
    models/
      __init__.py               # 显式 import 每个表模块并导出 Base——不这样写 Base.metadata 会是空的
      base.py                   # DeclarativeBase 声明基类,后面每张表模型都继承它
      enums.py                  # meal_slot/unit/source_tag 三组闭合取值,纯字符串元组
      meal_entry.py             # 餐次明细表模型(短期库,SPEC §4.1)
      daily_summary.py          # 每日汇总表模型(长期库,SPEC §4.2)
      chat_message.py           # 对话历史表模型(短期库,SPEC §6.4)
      food_base_cn.py           # 中国食物成分数据表模型(SPEC §4.4.1,本 PR 只建表不导数据)
      food_base_us.py           # USDA 食物数据缓存表模型(SPEC §4.4.2,本 PR 只建表不接 API)
    routers/
      __init__.py             
      health.py                 # GET /health 路由——具体作用见下方"health 是什么"一节
    schemas/
      __init__.py             
      health.py                 # HealthResponse:/health 接口返回体的 Pydantic 结构定义
  migrations/
    env.py                      # 改:接入 Base.metadata,让 alembic 能自动比对模型和库结构的差异
    versions/
      xxxx_create_demo_tables.py   # autogenerate 生成的第一条迁移脚本(建 5 张表),人工审查后保留
  requirements.txt              # 不改动——已有依赖清单(fastapi/sqlalchemy/alembic等)本 PR 全够用

frontend/
  package.json                  # 项目清单:依赖、devDependencies、npm scripts(dev/build/test)
  vite.config.ts                # Vite 构建配置:React 插件、PWA 插件、端口锁定、Vitest 测试配置
  vitest.setup.ts               # Vitest 全局测试环境初始化(引入 jest-dom 断言扩展)
  tsconfig.json / tsconfig.node.json   # TypeScript 编译配置(应用代码一套、Vite 配置自身一套)
  index.html                    # SPA 唯一 HTML 入口,挂载 React 根节点
  .env.example                  # 前端环境变量样例(VITE_API_BASE_URL 指向后端地址)
  public/
    icons/
      icon-192.png / icon-512.png / icon-maskable-512.png  # PWA 安装图标,占位纯色图,待真实品牌资源替换
  src/
    main.tsx                    # 前端入口:引入自托管字体/全局样式,挂载 <App/>
    App.tsx                     # 「记录」「看板」两 Tab 空壳 + 后端连通状态展示
    vite-env.d.ts                # Vite 客户端类型声明(让 TS 认识 import.meta.env 等)
    styles/
      tokens.css                 # design.md §2/§3 色板/字体/圆角等设计 token,CSS 变量形式
      global.css                 # 全局基础样式,把背景色/字体族接到 tokens.css 上
    lib/
      health.ts                  # 封装对后端 GET /health 的 fetch 调用,供 App.tsx 展示连通状态用

tests/
  backend/
    conftest.py                  # pytest fixture:在临时库上跑 alembic 迁移 + 可覆盖 DB 的 TestClient
    test_health.py               # 验证 GET /health 返回 200 且 body 里 db 状态正常
    test_schema.py                # 验证迁移建出的表结构符合 SPEC(字段可空性、无 user_id、CHECK 约束等)
  frontend/
    App.test.tsx                  # 验证两个 tab 标签都渲染、点击能切换 active 状态(mock 掉 fetch)

pyproject.toml                   # 新增,仓库根:pytest(pythonpath/testpaths)+ ruff + mypy 统一配置
tasks/current.md                 # 本计划内容的归档,作为当前活跃步骤的细粒度执行记录
docs/product/SPEC.md              # 改:meal_slot/source_tag 两处字面量同步(见下方"SPEC.md 同步")
tasks/STATUS.md                   # 改:1.8 行 source_tag 提法同步,和 SPEC 保持一致
AGENTS.md                        # 改:补齐"命令"占位段(起服务/跑测试/前端dev/lint 四行)
README.md                        # 改:快速开始补前端安装/启动/测试步骤
```

---

## "health" 是什么、为什么要有这个端点

`GET /health` 是后端服务的健康检查端点——业界通用模式,不是这个项目独有的概念:一个极
轻量的接口,专门用来回答"这个服务本身,以及它依赖的关键组件(这里是数据库),现在是不是
真的可用",而不是"进程有没有在跑"这种更弱的信号。在这个项目里它具体做两件事:

1. **证明后端骨架本身没搭错**——启动、配置加载、数据库连接这条链路里任何一环崩了,这个
   端点会第一时间暴露出来,而不是要等到某个真实业务请求失败才发现。
2. **是 SPEC §11.1 Demo 平台边界"建立可安装 PWA 与私有后端基础链路"这句话的具体落地**
   ——1.3 的前端空壳会在页面加载时真的去请求这个端点,并把结果(连通/不通)显示出来,
   用一次真实的网络请求证明"手机上的 PWA 真的能连到你自己的私有后端",而不是两边各自
   独立地"看起来能跑"。

`routers/health.py` 就是承载这一个端点的文件;之所以单独拆一个 `routers/` 目录而不是
写在 `main.py` 里,是因为后面每一步(1.9 起的 LLM 解析、1.11 起的写入路径……)都会往这个
目录加自己的路由文件,现在就分好目录省得以后手忙脚乱地拆分一个越写越大的 `main.py`。

---

## 1.1 后端骨架 + 健康检查

- `config.py`:`Settings(BaseSettings)` 含 `database_url: str`、`cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]`;`env_file` 用 `Path(__file__).resolve().parent.parent / ".env"` 绝对路径(不用裸 `".env"`,否则 uvicorn 从 `backend/` 启动、pytest 从仓库根启动时 cwd 不一致会读不到文件——这个写法直接照抄 `migrations/env.py` 已有的做法);`extra="ignore"`(`.env` 里未来会有 DASHSCOPE/USDA/BOCHA 等本 PR 不需要的 key,不能因为多余字段报错)。
- `db.py`:`create_engine(settings.database_url, connect_args={"check_same_thread": False})`;`SessionLocal`;`get_db()` 生成器,`yield` 后 `finally: close()`。**必须是可覆盖的独立依赖函数**——1.2 的 pytest 用 `app.dependency_overrides[get_db]` 把测试请求指向临时数据库,不能内联成 lambda。
- `routers/health.py`:`GET /health` 依赖 `get_db`,执行 `db.execute(text("SELECT 1"))` 验证数据库真的连得上(不只是"进程活着"),成功返回 `{"status":"ok","db":"ok"}`,失败返回 503 而不是让异常冒泡成裸 500。
- `main.py`:`create_app()` 装 CORS 中间件(允许来源=`settings.cors_origins`)+ 挂 `health` 路由;模块级 `app = create_app()` 供 `uvicorn app.main:app` 用。

## 1.2 Demo 数据模型 + 首条迁移

字段严格对齐 SPEC §4.1/4.2/6.4/4.4,不加 `user_id`,营养素字段一律 `nullable=True` 且不给默认值 0:

- **`meal_entry`**:id PK、date(TEXT,index)、meal_slot(枚举 **breakfast/lunch/dinner/other**,4档最后一档对应"加餐")、food_name、**quantity(REAL,允许小数——克数/份数都可能是 1.5 这种非整数,不加整数约束)**、unit(枚举 g/serving)、kcal/carb_g/protein_g/fat_g/fiber_g(REAL,nullable)、source_tag(枚举 chn_table/usda/**decompose_estimate**/user_create)、created_at。
- **`daily_summary`**:date(TEXT,主键)、total_kcal/total_carb_g/total_protein_g/total_fat_g/total_fiber_g(REAL,nullable)、bmr_snapshot(REAL,nullable)、updated_at。
- **`chat_message`**:id PK、date(index)、role(纯 TEXT,不设枚举——取值还没定死)、content、image_ref(nullable)、created_at。
- **`food_base_cn`**(已用真实样本文件核对字段:`foodCode`/`foodName`/`edible`/`energyKCal`/`protein`/`fat`/`CHO`/`dietaryFiber`,只投影 SPEC §4.4.1 要求的这几项,不带多余微量营养素):**用 surrogate id 主键 + `UniqueConstraint(food_code, source_commit)`,不用 `food_code` 单独做主键**——原因是 `docs/data/food_base-import-log.md` 明确设计成"重新锁定新 commit 时新建兄弟目录、不覆盖旧目录",如果表主键是 `food_code`,以后 1.4 的导入脚本就没法让新旧两个 commit 版本的同一 `food_code` 共存,等于现在就替它把这个决定焊死了。这个改动不影响本 PR 任何查询,留给 1.4 自己决定要不要真的并存。字段:food_code、food_name、edible_pct(REAL,原始百分数如 87.0)、kcal_100g/carb_100g/protein_100g/fat_100g/fiber_100g(REAL,nullable)、source_commit、created_at。
- **`food_base_us`**:`fdc_id` 直接做主键(USDA 的 fdcId 是真自然键,缓存语义就是按 fdc_id upsert,没有 food_base_cn 那种多版本共存问题)。data_type、description、kcal_100g/carb_100g/protein_100g/fat_100g/fiber_100g(REAL,nullable)、cached_at。
- 三个枚举字段(`meal_slot`/`unit`/`source_tag`)用 `sa.Enum(*values, native_enum=False, create_constraint=True)` 落成 SQLite 的 CHECK 约束——**`create_constraint=True` 必须显式给,SQLAlchemy 1.1 起非原生枚举方言默认是 False,不给的话 SQLite 端会静默退化成没有任何约束的普通 VARCHAR**。用纯字符串元组(`models/enums.py`)而不是 Python `enum.Enum` 类映射,避免 SQLAlchemy 默认存枚举成员名(大写)而不是 `.value`(小写)导致存进库里的值和 SPEC 定义的字面量对不上。
- `models/__init__.py` 必须显式 `import` 每一个表模块并 `__all__` 导出,只 import `Base` 不够——`Base.metadata` 要靠子模块的 `mapped_column` 声明执行过一遍才会有内容,不然 autogenerate 会静默生成一个空 diff。
- `migrations/env.py`:改 `target_metadata = Base.metadata`;两处 `context.configure(...)`(离线/在线)都加 `render_as_batch=True`——SQLite 不支持 `ALTER TABLE` 改约束/删列,第一条迁移用不上,但以后任何一次改表都需要,现在加成本为零,以后补代价更高。
- **生成迁移的具体步骤**:
  1. `cd backend`,`conda activate vibe-coding` 已激活的前提下,临时用环境变量指向一个一次性文件(不改 `.env`,不碰真实库来生成/试跑迁移):PowerShell 下 `$env:DATABASE_URL = "sqlite:///./data/_scaffold_autogen.db"; alembic revision --autogenerate -m "create demo tables"`。
  2. 生成后人工审查这个迁移文件:CHECK 约束是否都在、营养素字段是否都 nullable、有没有意外多出 `user_id`、`daily_summary` 主键是不是只有 `date`、枚举字面量是不是 `other`/`decompose_estimate` 而不是旧值。
  3. 删掉临时文件 `_scaffold_autogen.db`。
  4. 用下面 §测试 描述的 `tmp_path` pytest 验证迁移脚本本身能正确建表。
  5. 按你的决定,直接对 `backend/data/dietapp.db` 跑 `alembic upgrade head`(满足 `tasks/STATUS.md` 1.1 行"`alembic upgrade head` 可跑"这条验收),不再额外停下来确认。

## 1.3 前端 PWA 空壳

- `npm create vite@latest` 等效手搭 `frontend/`:React+TS,`vite-plugin-pwa` 管 manifest+SW(在 `vite.config.ts` 里内联配置 `manifest: {...}`,不手写 `public/manifest.webmanifest`,单一真源)。`server.strictPort = true`——端口冲突时直接报错,而不是 Vite 默默换到 5174 导致后端 CORS 白名单(写死 5173)悄悄拒绝所有请求却只在浏览器控制台报个含糊的 CORS 错误。
- 只做「记录」「看板」两个 Tab(Demo 阶段明确不启用「我的」,SPEC §11.1 已核实),`App.tsx` 里一个 `useState<"record"|"board">` 就够,不引入路由库。
- Tab 内容区先放占位文字,组件先不拆(`TabBar`/`HealthIndicator` 这类拆分等 1.14 真内容进来再做,现在拆是提前抽象但没有第二个调用点)。
- `App.tsx` 挂载时调用 `lib/health.ts` 的 `fetch(`${VITE_API_BASE_URL}/health`)`,展示一个极简连通状态文字("已连接后端"/"无法连接后端")——具体作用见上面"health 是什么"一节,这是 SPEC §11.1 要求的"PWA 与私有后端基础链路"的实际验证点,不是可选装饰。`frontend/.env.example` 写 `VITE_API_BASE_URL=http://localhost:8000`。
- `src/styles/tokens.css`:按 `design.md` §2/§3 落 CSS 变量——`--color-primary:#2E8B62`、`--color-primary-hover:#22704E`、`--color-bg:#EDF2E9`、`--color-card:#FFFFFF`、`--color-text-primary:#141E19`/`--color-text-secondary:#657469`/`--color-text-tertiary:#7C8A82`、`--radius-card:20px`、`--font-numeric:"DM Sans"`、`--font-text:"Noto Sans SC"`。字体走 `@fontsource/dm-sans`+`@fontsource/noto-sans-sc` npm 包自托管(避免外部字体 CDN 请求,PWA 离线外壳缓存更干净),只导入 design.md 实际用到的 400/500/700 三档字重文件,不导入 Noto Sans SC 的全量包(体积很大)。
- 图标资源:`public/icons/` 下放纯色占位 PNG(`#2E8B62` 实心方块,192px/512px),明确标注"占位,待真实品牌资源到位后替换"。
- **"可安装到手机主屏(粗验)"的验证方式**:桌面 Chrome DevTools 的 Application→Manifest 面板对着 `npm run build && npm run preview` 的产物检查(manifest 合法、可安装),不强求真机在局域网 HTTP 下安装——PWA 安装通常要 HTTPS,真机验证明确排到 1.14。

## SPEC.md 同步(本 PR 新增的小改动)

`docs/product/SPEC.md` 逐处修订(只改这 4 处,`food_favorite.category` 里那个不相关的
`snack` 不动):

- §4.1 `meal_entry` 表:`meal_slot | breakfast/lunch/dinner/snack` → `breakfast/lunch/dinner/other`;`source_tag | ...chn_table/usda/web_estimate/user_create` → `...chn_table/usda/decompose_estimate/user_create`。
- §4.5 `food_favorite` 表(仅文字层面同步概念,不代表本 PR 建这张表):`web_estimate 保存后仍保持该值` → `decompose_estimate 保存后仍保持该值`。
- §7.8 来源与缺失值:`` `web_estimate` 永久保留风险标记 `` → `` `decompose_estimate` 永久保留风险标记 ``。
- §8.5 第④级拆解契约:``source_tag = web_estimate`` → ``source_tag = decompose_estimate``。

`docs/decisions/0002-composed-dish-fallback.md` 里也提到旧值 `web_estimate`(它是历史决策
记录,记的是"当时为什么这么定",不做事后编辑)。`tasks/STATUS.md` 1.8 行的提法一并改成
`decompose_estimate`,那是我自己维护的进度表,不是历史记录,理应保持和 SPEC 一致。

## 跨领域:测试与 lint 基础设施

- 仓库根新增 `pyproject.toml`:
  - `[tool.pytest.ini_options]`:`pythonpath = ["backend"]`、`testpaths = ["tests/backend"]`、`addopts = ["--import-mode=importlib"]`(比默认 `prepend` 模式更抗"以后 tests/ 拆出验收/单元/集成子目录、同名测试文件"这种以后大概率发生的情况)。
  - `[tool.ruff]` / `[tool.ruff.lint]`:`target-version="py311"`,排除 `backend/migrations/versions`。
  - `[tool.mypy]`:`python_version="3.11"`,`mypy_path="backend"`,`files=["backend/app"]`。
- `tests/backend/conftest.py`:
  - 构造临时 SQLite URL 时用 `(tmp_path / "test.db").as_posix()` 拼 `sqlite:///...`,不能裸 f-string 拼 `WindowsPath`——Windows 反斜杠会拼出非法 URI。
  - fixture:`Config("backend/alembic.ini")` → `set_main_option("sqlalchemy.url", tmp_db_url)` → `command.upgrade(cfg, "head")`,跑完把 engine/url 交给测试用。
  - fixture:`TestClient(app)`,配 `app.dependency_overrides[get_db]` 指向临时库的 session,teardown 清理 override。
- `tests/backend/test_schema.py`:对临时库跑完迁移后用 `sqlalchemy.inspect()` 断言——5 张表都在;营养素字段 `nullable=True`;没有任何表带 `user_id`;`daily_summary` 主键是 `["date"]`;`meal_entry.meal_slot`/`source_tag` 的 CHECK 约束里出现的是新字面量(`other`/`decompose_estimate`)而不是旧值;**外加一条**`inspector.get_check_constraints("meal_entry")` 里能看到三个枚举对应的 CHECK 约束(专门抓"忘记写 `create_constraint=True`"这个最容易犯的错,不然列看着正常但约束其实没生效,测试会假绿)。
- `tests/backend/test_health.py`:`TestClient` 打 `GET /health`,断言 200 且 body 是 `{"status":"ok","db":"ok"}`。
- 前端测试放 **`tests/frontend/App.test.tsx`**(你已确认按 AGENTS.md 现有字面约定走,不用 `frontend/src/` 同目录的省配置写法)。`frontend/vite.config.ts` 的 `test.include` 用相对路径指向 `../tests/frontend/**/*.{test,spec}.{ts,tsx}`,并加 `resolve.alias: { "@": path.resolve(__dirname, "src") }` 让测试文件能用 `@/App` 而不是拼相对路径。**这条路径写法在这台机器上还没实跑验证过**——执行阶段第一件事就是先跑通这一条,如果 Vitest 认不到仓库外的 include glob,会回来跟你说明情况、退回到 `frontend/src/` 同目录方案,不会卡在这卡很久硬啃。测试内容:两个 tab 标签都渲染、点击后 `aria-selected` 切换;渲染前 `vi.stubGlobal("fetch", ...)` mock 掉,不让测试真的发网络请求。

## 文档更新(最后做,等命令都跑通了再写)

- `AGENTS.md`「命令」段落补齐:后端起服务(`conda activate vibe-coding && cd backend && uvicorn app.main:app --reload`)、跑测试(根目录 `pytest` / `cd frontend && npm test`)、前端 dev(`cd frontend && npm run dev`)、lint(`ruff check backend && mypy` + 备注前端 ESLint 留后续 PR)。
- `README.md` 快速开始补前端一段(`npm install`/`cp .env.example .env`/`npm run dev`)和测试命令。

---

## 顺序

1. `git checkout -b feature_demo_01_scaffold`(从最新 main)。
2. 写 `tasks/current.md`(本计划内容)。
3. SPEC.md + STATUS.md 的字面量同步(小改动,先落地,后面写模型时直接抄新字面量)。
4. 1.1 后端骨架(不依赖 1.2,`/health` 的 `SELECT 1` 在空库上也能跑)。
5. 1.2 模型 + 生成迁移(对临时文件生成、审查)+ `tests/backend/` 验证 + 对真实 `dietapp.db` 跑 `alembic upgrade head`。
6. 1.3 前端空壳,先验证 `tests/frontend/` 的跨目录 include 写法能不能跑通。
7. 根 `pyproject.toml`(实际上 4-5 步过程中就要有,不是最后补)。
8. 全部测试跑绿、贴命令+输出。
9. 补 `AGENTS.md`/`README.md` 文档。
10. 不自动 `git push` / 不自动开 PR——这两步各自单独确认。

## 验证方式

- 后端:`conda activate vibe-coding && pytest`(根目录跑,覆盖 `tests/backend/` 全部用例)+ `ruff check backend` + `mypy`。
- 前端:`cd frontend && npm run build`(验证 TS 编译+PWA 插件不报错)、`npm test`(Vitest)、`npm run dev` 手动看两个 tab 能点、`/health` 连通状态能显示。
- 端到端粗验:后端 `uvicorn` 起服务 + 前端 `npm run dev` 同时跑,浏览器打开前端页面确认连通状态显示"已连接"(证明 CORS 和 `VITE_API_BASE_URL` 配置对)。
