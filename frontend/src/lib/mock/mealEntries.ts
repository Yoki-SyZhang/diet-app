// mock 版 /meal-entries/*,顶替 backend/app/routers/meal_entries.py +
// services/meal_entry_write.py。保留两条关键语义:
//   - 幂等:同一 confirmation_id 只写一行,重试返回已有记录;
//   - kcal 为 null 拒绝写入(SPEC §7.6 / AGENTS.md 铁律「未拿到可信营养结果不写库」)。

import type { ConfirmMealEntryRequest, MealEntryOut } from '@/types/diet'
import { attributionDate, fakeLatency, utcNowIso } from './attribution'
import { loadState, mutate } from './store'

const SLOT_ORDER = ['breakfast', 'lunch', 'dinner', 'other']

/** POST /meal-entries */
export async function confirmMealEntry(
  request: ConfirmMealEntryRequest,
): Promise<MealEntryOut> {
  await fakeLatency(250)
  const now = new Date(request.now_utc)
  const at = Number.isNaN(now.getTime()) ? new Date() : now

  return mutate((state) => {
    const existing = state.entries.find(
      (entry) => entry.confirmation_id === request.confirmation_id,
    )
    if (existing) return existing

    const { preview } = request
    if (preview.nutrients.kcal === null) {
      throw new Error(`写入失败(HTTP 422)`)
    }

    const entry: MealEntryOut = {
      id: state.nextEntryId++,
      confirmation_id: request.confirmation_id,
      // 归属日由这次批量确认的统一时刻决定,和后端一样不自己读当前时刻
      date: attributionDate(at),
      meal_slot: preview.meal_slot,
      food_name: preview.food_name,
      quantity: preview.quantity,
      unit: preview.unit,
      kcal: preview.nutrients.kcal,
      carb_g: preview.nutrients.carb_g,
      protein_g: preview.nutrients.protein_g,
      fat_g: preview.nutrients.fat_g,
      fiber_g: preview.nutrients.fiber_g,
      source_tag: preview.source_tag,
      created_at: utcNowIso(at),
    }
    state.entries.push(entry)
    return entry
  }, at)
}

/** GET /meal-entries/today —— 按餐次顺序、组内按 id,和 list_today_meal_entries 一致。 */
export async function fetchTodayEntries(): Promise<MealEntryOut[]> {
  const now = new Date()
  const today = attributionDate(now)
  return loadState(now)
    .entries.filter((entry) => entry.date === today)
    .sort(
      (a, b) =>
        SLOT_ORDER.indexOf(a.meal_slot) - SLOT_ORDER.indexOf(b.meal_slot) || a.id - b.id,
    )
}

/** DELETE /meal-entries/{id} —— true=删掉了,false=本来就不在(对应 404)。 */
export async function deleteMealEntry(entryId: number): Promise<boolean> {
  await fakeLatency(200)
  const now = new Date()
  const today = attributionDate(now)
  return mutate((state) => {
    const index = state.entries.findIndex(
      (entry) => entry.id === entryId && entry.date === today,
    )
    if (index === -1) return false
    state.entries.splice(index, 1)
    return true
  }, now)
}
