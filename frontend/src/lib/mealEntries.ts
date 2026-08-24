// 1.9 今日明细 API(backend/app/routers/meal_entries.py)。POST 幂等:同一
// confirmation_id 重试不会写出第二行,网络抖动可放心重试。

import type { ConfirmMealEntryRequest, MealEntryOut } from '@/types/diet'

function baseUrl(): string {
  return import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
}

export async function confirmMealEntry(request: ConfirmMealEntryRequest): Promise<MealEntryOut> {
  const response = await fetch(`${baseUrl()}/meal-entries`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })
  if (!response.ok) {
    throw new Error(`写入失败(HTTP ${response.status})`)
  }
  return (await response.json()) as MealEntryOut
}

export async function fetchTodayEntries(): Promise<MealEntryOut[]> {
  const response = await fetch(`${baseUrl()}/meal-entries/today`)
  if (!response.ok) {
    throw new Error(`查询失败(HTTP ${response.status})`)
  }
  return (await response.json()) as MealEntryOut[]
}

/** 204 → true;404(记录已不存在/非今日)→ false;其余错误抛 Error。 */
export async function deleteMealEntry(entryId: number): Promise<boolean> {
  const response = await fetch(`${baseUrl()}/meal-entries/${entryId}`, { method: 'DELETE' })
  if (response.status === 204) return true
  if (response.status === 404) return false
  throw new Error(`删除失败(HTTP ${response.status})`)
}
