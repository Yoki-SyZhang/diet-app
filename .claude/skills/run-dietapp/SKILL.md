---
name: run-dietapp
description: 启动并驱动 DietApp 做浏览器冒烟测试(run/start/screenshot/smoke)。后端 uvicorn 指向 SQLite 副本库 + 前端 vite dev,用 driver.py(playwright + 系统 Chrome)驱动记录页交互并截图。要在真实浏览器里验证改动、跑某个里程碑的手动冒烟、或截图 UI 时用这个。
---

DietApp 是单用户减脂 PWA(FastAPI + SQLite 后端、React/Vite 前端)。agent 驱动方式:两个服务后台起好后,跑 `.claude/skills/run-dietapp/driver.py`(playwright 装在外置目录、驱动系统 Chrome headless),按场景交互并截图。**冒烟一律用副本库,绝不把 `DATABASE_URL` 指向真实库 `backend/data/dietapp.db`**——触碰真实库/跑真实迁移按 AGENTS.md 需用户明确确认。

所有路径相对仓库根。Python 一律用完整路径 `C:\Python\Anaconda\envs\vibe-coding\python.exe`(非交互 shell 里 `conda activate` 会报 `Run 'conda init'`,不可用)。

## Prerequisites(一次性)

系统已装 Chrome(`C:\Program Files\Google\Chrome`)。playwright 装到外置目录,不污染 vibe-coding 环境(本机没有 chromium-cli,故用 playwright + `channel="chrome"`,无需下载 playwright 自带浏览器):

```powershell
& C:\Python\Anaconda\envs\vibe-coding\python.exe -m pip install --target "$env:LOCALAPPDATA\dietapp-pwlib" playwright --quiet
```

driver.py 从 `%LOCALAPPDATA%\dietapp-pwlib` 读库(可用环境变量 `DIETAPP_PWLIB` 覆盖)。LLM 功能需要 `backend/.env` 已配 `DASHSCOPE_API_KEY`(用户自行管理,不要动 .env)。

## Setup(每次冒烟)

复制真实库为副本并把副本迁到 head(`DATABASE_URL` 用进程环境变量传——pydantic-settings 里环境变量优先于 .env,不用改文件):

```powershell
Copy-Item backend/data/dietapp.db backend/data/dietapp.dev.db -Force
Set-Location backend; $env:DATABASE_URL='sqlite:///./data/dietapp.dev.db'; & C:\Python\Anaconda\envs\vibe-coding\Scripts\alembic.exe upgrade head; Set-Location ..
```

## Run (agent path)

两个服务各自后台启动(bash 语法;前端端口 5173 是 strictPort):

```bash
cd backend && DATABASE_URL='sqlite:///./data/dietapp.dev.db' /c/Python/Anaconda/envs/vibe-coding/Scripts/uvicorn.exe app.main:app --host 127.0.0.1 --port 8000
```

```bash
cd frontend && npm run dev
```

轮询就绪(不要瞎 sleep):

```bash
for i in $(seq 1 30); do curl -sf http://127.0.0.1:8000/health >/dev/null && curl -sf http://127.0.0.1:5173 >/dev/null && echo "both up" && break; sleep 1; done
```

驱动(默认 smoke;截图落在 `.claude/skills/run-dietapp/screenshots/`,已 gitignore;结尾打印 console error,有 error 不算通过):

```powershell
& C:\Python\Anaconda\envs\vibe-coding\python.exe .claude\skills\run-dietapp\driver.py smoke
```

| 场景 | 内容 |
|---|---|
| `smoke` | 打开记录页 → 发一句闲聊 → 等 AI 回复 → 截图(默认;1 次真实 LLM 调用) |
| `happy` | 多食物识别 → 暂存确认+暂存修改 → 两轮顶部确认 → 恰好一条总结气泡 |
| `clarify_chitchat` | 追问循环 / 顶部放弃 / 闲聊 / 改已有记录被拒 |
| `delete_row` | 今日明细删一行(先跑 happy 才有行) |
| `guard` | 有未确认项时直接打字 → 拦截弹窗 → 放弃并继续 |
| `resume_setup` → `resume` | 制造未收尾批次 → 重开页面恢复弹窗 → 继续/收尾/不再弹 |

停止 + 清理(按端口杀,理由见 Gotchas):

```powershell
Get-NetTCPConnection -LocalPort 8000,5173 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
Remove-Item backend/data/dietapp.dev.db -Force
```

## Run (human path)

真实日常使用走真实库:`conda activate vibe-coding && cd backend && uvicorn app.main:app --reload` + `cd frontend && npm run dev`,浏览器开 http://localhost:5173。agent 冒烟不要走这条。

## Test

```powershell
& C:\Python\Anaconda\envs\vibe-coding\python.exe -m pytest -q          # 后端,235 passed(llm_live 默认 deselect)
Set-Location frontend; npm test; Set-Location ..                        # 前端,37 passed
```

真实 LLM 冒烟(产生 API 费用):`pytest -m llm_live`。

## Gotchas

- **停服务必须按端口杀**——TaskStop/杀 npm 包装进程杀不掉 vite 子进程,孤儿 node 占着 5173,下次启动 strictPort 直接 `EADDRINUSE` 退出。上面的 `Get-NetTCPConnection` 一条清两个端口。
- **LLM 延迟**:解析+逐项估算一步可达几十秒,driver 里等待统一 90s;自己写断言别用短超时。
- **打开页面后先等 ~2.5s** 再数气泡:挂载时拉历史消息是异步的,立刻计数基线是 0,后续断言全错位(driver 的 `open_app` 已内置)。
- **后端 uvicorn 没开 --reload**:改了 backend 代码/prompt 要手动重启;前端 vite HMR 自动生效。
- **PowerShell 5.1 内嵌中文 JSON 会被编码搞坏**(curl 一行流报 "error parsing the body"):要手动调接口时把 body 写进 UTF-8 文件再 `curl --data-binary @file`,或直接写 python 脚本。
- **迁移安全模式**:所有迁移对非空 `meal_entry`/`chat_message` 一律 raise 拒绝,升级副本失败先查表里是不是有上次没清的数据。

## Troubleshooting

- **`CondaError: Run 'conda init' before 'conda activate'`**:非交互 shell 不能 activate。用完整路径 `C:\Python\Anaconda\envs\vibe-coding\python.exe` / `...\Scripts\uvicorn.exe` / `...\Scripts\alembic.exe`。
- **前端起不来,输出尾部是 vite listen 报错**:5173 被孤儿进程占用,跑上面"停止"里的按端口杀,再重启。
- **driver 报 `ModuleNotFoundError: playwright`**:外置目录没装或被清,重跑 Prerequisites 那条 pip。
