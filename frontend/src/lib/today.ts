// 当前归属日(backend/app/routers/today.py)。前端不自己算归属日:偏移量和时区是
// 后端配置(SPEC §6.1),复算就成了第二份结转规则(.claude/rules/frontend.md)。

import type { TodayOut } from '@/types/diet'

function baseUrl(): string {
  return import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
}

export async function fetchToday(): Promise<TodayOut> {
  const response = await fetch(`${baseUrl()}/today`)
  if (!response.ok) {
    throw new Error(`查询失败(HTTP ${response.status})`)
  }
  return (await response.json()) as TodayOut
}
