# Vercel 公开演示版(`vercel-display` 分支)

一个**只有前端**的可交互演示:真实跑的是 DietApp 的 React PWA,后端换成浏览器里的
mock。给人点开链接就能把「说一句吃了什么 → 识别 → 确认 → 进今日明细 → 删除」走一遍,
不需要任何后端、账号或 API Key。

## 边界(这套东西**不**做什么)

- 不部署、不连接真实 FastAPI;产物里没有任何后端地址(见下面的验收命令)。
- 不上传、不访问真实 SQLite。
- 不调用真实 LLM / DashScope,不含任何 API Key。
- 访问者的数据只写进**他自己浏览器的 localStorage**,互相之间看不到,也不回传。

## 分支约定(重要)

- `vercel-display` 是**长期演示分支**,从业务分支切出来,只多不少:所有 mock 和
  Vercel 配置都只存在于这里。
- **不要把 `vercel-display` 合回 `main` 或 `feature_demo_*`**。
- 业务功能做完之后,是让 `vercel-display` 去 rebase/merge 目标业务分支来同步,
  方向永远是单向的:业务分支 → 演示分支。
- 为了让这件事一直好做,正式 API 模块 `frontend/src/lib/{chat,health,mealEntries,today}.ts`
  在本分支上**一个字都没改**,切换只发生在 `frontend/src/lib/api.ts`(见下)。

## 数据源怎么切

```
组件 ──> src/lib/api.ts ──┬── VITE_DATA_SOURCE=mock ──> src/lib/mock/*(不发网络请求)
                          └── 其它/未设置        ──> src/lib/{chat,mealEntries,today,health}.ts(真实 FastAPI)
```

`src/lib/dataSource.ts` 里的 `isDemoMode` 是**构建时**常量,不是运行时判断,所以
production 打包会把没选中的那一支整个摇掉。

默认值定在 **`frontend/vite.config.ts`**(`dataSource(mode)`),production 构建默认
`mock`。**刻意没用 `.env.production`**:仓库根 `.gitignore` 第 26 行的 `.env.*` 会把
那个文件挡在 git 之外,Vercel 上根本拿不到,构建出来反而是连真实后端的版本——而且
本地怎么跑都正常,极难发现。

| 场景 | 命令 | 走哪条 |
|---|---|---|
| 本地日常开发 | `npm run dev` | 真实 FastAPI(`.env` 里的 `VITE_API_BASE_URL`) |
| 前端测试 | `npm test` | 真实 HTTP 路径(既有用例 stub `fetch`);mock 由 `demo_mock_data_source.test.ts` 单独覆盖 |
| production 打包 / Vercel | `npm run build` | mock(`vite.config.ts` 里 production 默认 `mock`) |
| 本地看演示版 | `npm run build && npm run preview` | mock,和 Vercel 托管的是同一份产物 |

本地想在 dev server 里试 mock:`VITE_DATA_SOURCE=mock npm run dev`
(PowerShell:`$env:VITE_DATA_SOURCE='mock'; npm run dev`)。显式给了就用给的,
不受上面那个默认值影响。

## Vercel 导入设置

在 Vercel 里 **Add New → Project → 导入本仓库**,然后:

| 项 | 值 |
|---|---|
| Root Directory | **`frontend`**(必须改,仓库根不是前端目录) |
| Framework Preset | Vite(`frontend/vercel.json` 已声明,一般会自动带出) |
| Build Command | `npm run build`(默认即可) |
| Output Directory | `dist`(默认即可) |
| Production Branch | `vercel-display`(Settings → Git,**别用 `main`**) |
| Environment Variables | **一个都不要加**。尤其不要配 `VITE_API_BASE_URL` —— 演示版不应指向任何真实后端;mock 开关由 `vite.config.ts` 提供,不依赖面板配置 |

`frontend/vercel.json` 里只有三件事:SPA 回退(刷新子路径不 404)、静态资源长缓存、
`sw.js` 不缓存(PWA `registerType: 'autoUpdate'` 要靠它拿到新版本)。

## 验收(改完 mock 后重跑这一串)

```bash
cd frontend
npm test          # 含 src/tests/demo_mock_data_source.test.ts
npm run lint
npm run build
```

产物里不该出现后端地址或密钥:

```bash
grep -rn "localhost\|127\.0\.0\.1\|:8000" dist/            # 期望:无输出
grep -rniE "dashscope|sk-[a-z0-9]{10,}|api[_-]?key" dist/assets/*.js   # 期望:无输出
```

浏览器闭环冒烟(跑的是 `dist`,即 Vercel 实际托管的那份):

```bash
cd frontend && npm run preview      # 4173
```

```powershell
$env:DIETAPP_APP_URL='http://127.0.0.1:4173'
& C:\Python\Anaconda\envs\vibe-coding\python.exe .claude\skills\run-dietapp\driver.py demo_mock
```

细节和坑见 `.claude/skills/run-dietapp/SKILL.md` 的「Mock 演示模式」一节。

## mock 覆盖到哪一步

`frontend/src/lib/mock/` 顶替的是后端这几个文件,行为(包括播报/总结文案的确定性
口径、幂等键、归属日)都照抄:

| mock | 顶替 |
|---|---|
| `chat.ts` | `routers/chat.py` + `services/chat_turn.py`(识别播报、修改重估、批次总结、未完成批次) |
| `mealEntries.ts` | `routers/meal_entries.py` + `services/meal_entry_write.py`(幂等写入、今日查询、删除) |
| `system.ts` | `routers/today.py`、`routers/health.py` |
| `foods.ts` | `services/nl_parse.py` + `services/food_estimate.py`(规则解析 + 一张演示用营养表) |
| `attribution.ts` | `services/attribution.py`(归属日 = date(本地时间 − 2h)) |
| `store.ts` | SQLite(整份状态一个 JSON,存 localStorage) |

演示里能真的做到:种子对话+今日明细、多食物识别并各自绑定份量、量词折算
(两个蛋=100g / 一杯牛奶=250g)、暂存确认、修改重估、批量写入、批次总结、
今日明细删除、刷新恢复未完成批次、跨天自动重新播种。

**不覆盖**:看板/我的两个 Tab(业务上本来就还没实现)、真实食物库四级查询链、
结转任务。`foods.ts` 里的营养数值是演示量级,**不是可信营养数据**,也不是
`food_base_cn/us` 快照的子集。

## 页面上怎么表明这是演示

- 顶栏常驻琥珀色徽标:**Mock 演示模式 · 数据仅存本机**,旁边是「重置演示数据」。
  `/health` 的 mock 返回 `'demo'` 而不是 `'ok'`,所以这里**不会**显示成「已连接后端」。
- 首条助手消息说明数据只在本地、不调用真实模型。
- 解析卡片每一项的小字是「演示估算 · 可能不准」(真实模式下才是「网络估算」)。
