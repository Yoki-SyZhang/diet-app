// vercel-display 专属:数据源开关。
//
// 正式分支上前端只有一条路——打 HTTP 给本地 FastAPI。演示分支多一条 mock 路,
// 但**不改写正式 API 模块**:`lib/{chat,health,mealEntries,today}.ts` 在这个分支上
// 保持和业务分支逐字节一致(方便以后 rebase 不冲突),切换只发生在 `lib/api.ts`。
//
// 取值来自构建时环境变量,不是运行时判断:
// - 本地 `npm run dev` / `npm test`  → 未设置 → 走真实 FastAPI(现状不变)
// - `npm run build`(含 Vercel)      → `.env.production` 里 VITE_DATA_SOURCE=mock → 走 mock
//
// VITE_* 会被原样编译进前端产物,**任何情况下都不能往里放服务端密钥**
// (DASHSCOPE_API_KEY 之类只存在于 backend/.env,演示分支根本不接 LLM)。
export const isDemoMode = import.meta.env.VITE_DATA_SOURCE === 'mock'
