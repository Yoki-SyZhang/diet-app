// vercel-display 专属:mock 数据源。测的是「演示版能不能真的走完一遍闭环」——
// 输入 → 识别 → 确认写入 → 今日明细 → 删除 → recap,外加幂等/未完成批次/持久化。
//
// 命名没跟 `demo_<NN>_` 的约定(AGENTS.md / tasks/STATUS.md):那个 NN 取自
// `feature_demo_NN_*` 分支号,而 mock 不属于任何业务 PR,只活在演示分支上。
//
// 直接测 `@/lib/mock/*` 而不是 `@/lib/api`:api.ts 的分支由构建时常量
// VITE_DATA_SOURCE 决定,测试环境里它是 undefined(走真实 HTTP,由既有的
// demo_04_* 用例覆盖),所以这里绕过门面直接打 mock 实现。

import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  fetchOpenBatch,
  fetchTodayMessages,
  sendChatMessage,
  sendModifyCorrection,
  sendRecap,
} from '@/lib/mock/chat'
import {
  confirmMealEntry,
  deleteMealEntry,
  fetchTodayEntries,
} from '@/lib/mock/mealEntries'
import { fetchToday } from '@/lib/mock/system'
import { resetState } from '@/lib/mock/store'
import { attributionDate } from '@/lib/mock/attribution'
import type { ConfirmableItem } from '@/types/diet'

const NOW = () => new Date().toISOString()

function confirmRequest(item: ConfirmableItem) {
  return {
    confirmation_id: item.confirmation_id,
    preview: item.outcome.preview!,
    now_utc: NOW(),
  }
}

beforeEach(() => {
  resetState()
})

describe('mock 种子数据', () => {
  it('首次打开就有今日对话和早餐明细,且不弹「继续上次」', async () => {
    const messages = await fetchTodayMessages()
    const entries = await fetchTodayEntries()

    expect(messages[0].content).toContain('Mock 演示模式')
    expect(messages.map((m) => m.kind)).toContain('recognition')
    expect(entries.map((e) => e.food_name)).toEqual(['水煮蛋', '牛奶'])
    expect(entries.every((e) => e.meal_slot === 'breakfast')).toBe(true)
    // 种子批次已收尾(有 recap + 明细都写了),不该打扰新访客
    expect(await fetchOpenBatch()).toBeNull()
  })

  it('归属日来自 mock 自己的时钟,不是自然日历日', async () => {
    const today = await fetchToday()
    expect(today.date).toBe(attributionDate())
    expect(() => Date.parse(today.date)).not.toThrow()
  })
})

describe('识别', () => {
  it('一句话里的多样食物各自绑定自己的份量', async () => {
    const response = await sendChatMessage('午餐吃了200g米饭和一份西兰花')

    expect(response.intent).toBe('new_entry')
    expect(response.outcome).toBe('resolved')
    expect(response.batch_id).not.toBeNull()
    expect(response.items).toHaveLength(2)

    const [rice, broccoli] = response.items.map((item) => item.outcome.preview!)
    expect(rice.food_name).toBe('米饭')
    expect(rice.quantity).toBe(200)
    expect(rice.nutrients.kcal).toBe(232)
    expect(rice.meal_slot).toBe('lunch')
    // 「一份」属于西兰花,不能被前面的米饭抢走
    expect(broccoli.food_name).toBe('西兰花')
    expect(broccoli.quantity).toBe(180)

    expect(response.assistant_message.content).toContain('我识别到了(午餐)')
    expect(response.assistant_message.kind).toBe('recognition')
  })

  it('数量写在食物后面也认(「米饭200g」)', async () => {
    const response = await sendChatMessage('晚饭吃了米饭250g')
    const preview = response.items[0].outcome.preview!
    expect(preview.quantity).toBe(250)
    expect(preview.meal_slot).toBe('dinner')
  })

  it('量词按食物折算克重(两个蛋 = 100g、一杯牛奶 = 250g)', async () => {
    const response = await sendChatMessage('早餐吃了两个水煮蛋和一杯牛奶')
    const quantities = response.items.map((item) => item.outcome.preview!.quantity)
    expect(quantities).toEqual([100, 250])
  })

  it('缺失营养素保持 null,不用 0 顶替', async () => {
    const response = await sendChatMessage('早餐吃了两个水煮蛋')
    const nutrients = response.items[0].outcome.preview!.nutrients
    expect(nutrients.fiber_g).toBeNull()
    expect(nutrients.kcal).toBe(147)
  })

  it('没提食物的闲聊不产出卡片', async () => {
    const response = await sendChatMessage('你好啊')
    expect(response.intent).toBe('no_log_intent')
    expect(response.batch_id).toBeNull()
    expect(response.items).toHaveLength(0)
  })

  it('说了吃但没说多少 → 追问,不产出卡片', async () => {
    const response = await sendChatMessage('中午吃了一些米饭')
    expect(response.outcome).toBe('needs_clarification')
    expect(response.items).toHaveLength(0)
    expect(response.assistant_message.content).toContain('多少')
  })

  it('认不出的食物走兜底估算,置信度标 low', async () => {
    const response = await sendChatMessage('午餐吃了150g佛跳墙')
    expect(response.items).toHaveLength(1)
    const preview = response.items[0].outcome.preview!
    expect(preview.confidence).toBe('low')
    expect(preview.quantity).toBe(150)
    expect(preview.nutrients.kcal).not.toBeNull()
  })
})

describe('写入 / 删除', () => {
  it('确认后进今日明细,同一 confirmation_id 重复提交不会写出第二行', async () => {
    const response = await sendChatMessage('午餐吃了200g米饭')
    const item = response.items[0]

    const written = await confirmMealEntry(confirmRequest(item))
    expect(written.food_name).toBe('米饭')
    expect(written.kcal).toBe(232)
    expect(written.date).toBe(attributionDate())

    const retried = await confirmMealEntry(confirmRequest(item))
    expect(retried.id).toBe(written.id)

    const entries = await fetchTodayEntries()
    expect(entries.filter((e) => e.confirmation_id === item.confirmation_id)).toHaveLength(1)
    expect(entries).toHaveLength(3) // 2 条种子 + 这条
  })

  it('删除只删掉那一行,重复删返回 false(对应 404)', async () => {
    const before = await fetchTodayEntries()
    expect(await deleteMealEntry(before[0].id)).toBe(true)
    expect(await deleteMealEntry(before[0].id)).toBe(false)

    const after = await fetchTodayEntries()
    expect(after.map((e) => e.id)).toEqual(before.slice(1).map((e) => e.id))
  })

  it('kcal 缺失拒绝写入(SPEC §7.6)', async () => {
    const response = await sendChatMessage('午餐吃了200g米饭')
    const item = response.items[0]
    const preview = { ...item.outcome.preview!, nutrients: { ...item.outcome.preview!.nutrients, kcal: null } }
    await expect(
      confirmMealEntry({ confirmation_id: item.confirmation_id, preview, now_utc: NOW() }),
    ).rejects.toThrow()
  })
})

describe('修改重新估算', () => {
  it('只改份量:食物名沿用,营养按新克重重算', async () => {
    const response = await sendChatMessage('午餐吃了200g米饭')
    const item = response.items[0]

    const result = await sendModifyCorrection({
      confirmation_id: item.confirmation_id,
      original_item: item.outcome.parsed_item,
      meal_slot: 'lunch',
      correction_text: '改成300g',
    })

    expect(result.success).toBe(true)
    expect(result.confirmation_id).toBe(item.confirmation_id)
    expect(result.outcome!.preview!.food_name).toBe('米饭')
    expect(result.outcome!.preview!.quantity).toBe(300)
    expect(result.outcome!.preview!.nutrients.kcal).toBe(348)
  })

  it('换食物但没说份量:沿用原来的克重', async () => {
    const response = await sendChatMessage('午餐吃了200g米饭')
    const item = response.items[0]

    const result = await sendModifyCorrection({
      confirmation_id: item.confirmation_id,
      original_item: item.outcome.parsed_item,
      meal_slot: 'lunch',
      correction_text: '其实是蛋炒饭',
    })

    expect(result.success).toBe(true)
    expect(result.outcome!.preview!.food_name).toBe('蛋炒饭')
    expect(result.outcome!.preview!.quantity).toBe(200)
  })

  it('听不懂的修正说明返回失败原因,不瞎猜', async () => {
    const response = await sendChatMessage('午餐吃了200g米饭')
    const item = response.items[0]

    const result = await sendModifyCorrection({
      confirmation_id: item.confirmation_id,
      original_item: item.outcome.parsed_item,
      meal_slot: 'lunch',
      correction_text: '今天天气不错',
    })

    expect(result.success).toBe(false)
    expect(result.outcome).toBeNull()
    expect(result.failure_reason).toBeTruthy()
  })
})

describe('批次收尾 / 未完成批次恢复', () => {
  it('识别完还没处理 → 报未完成批次;收尾后不再报', async () => {
    const response = await sendChatMessage('午餐吃了200g米饭和一份西兰花')

    const open = await fetchOpenBatch()
    expect(open?.batch_id).toBe(response.batch_id)
    expect(open?.items).toHaveLength(2)

    await sendRecap({
      batch_id: response.batch_id!,
      meal_slot: 'lunch',
      items: [{ food_name: '米饭', quantity: 200, state: 'confirmed', kcal: 232 }],
      now_utc: NOW(),
    })

    expect(await fetchOpenBatch()).toBeNull()
  })

  it('快照里每项都已写入 → 只是 recap 没送达,不打扰用户', async () => {
    const response = await sendChatMessage('午餐吃了200g米饭')
    await confirmMealEntry(confirmRequest(response.items[0]))
    expect(await fetchOpenBatch()).toBeNull()
  })

  it('recap 文案抄后端确定性口径,已记录/已放弃都点名', async () => {
    const response = await sendChatMessage('午餐吃了200g米饭和一份西兰花')
    const recap = await sendRecap({
      batch_id: response.batch_id!,
      meal_slot: 'lunch',
      items: [
        { food_name: '米饭', quantity: 200, state: 'confirmed', kcal: 232 },
        { food_name: '西兰花', quantity: 180, state: 'abandoned' },
      ],
      now_utc: NOW(),
    })

    expect(recap.assistant_message.kind).toBe('recap')
    expect(recap.assistant_message.content).toBe(
      '本轮处理完成。已记录:米饭200g(约232kcal)。已放弃:西兰花180g。',
    )
  })
})

/** 最小可用 Storage。
 *
 *  本来该直接用 jsdom 的 localStorage,但 Node 25 默认往 globalThis 上挂了一个
 *  实验性 localStorage,没给 `--localstorage-file` 时它的方法全是 undefined,而且
 *  把 jsdom 那个挡住了(跑测试时的 `--localstorage-file was provided without a
 *  valid path` 警告就是它)。所以这里自己塞一个真能用的进去——要测的本来也是
 *  「store 有没有走 Storage 接口」,不是 jsdom 自己好不好使。 */
function memoryStorage(): Storage {
  const map = new Map<string, string>()
  return {
    get length() {
      return map.size
    },
    key: (index: number) => [...map.keys()][index] ?? null,
    getItem: (key: string) => map.get(key) ?? null,
    setItem: (key: string, value: string) => void map.set(key, value),
    removeItem: (key: string) => void map.delete(key),
    clear: () => map.clear(),
  }
}

describe('持久化', () => {
  it('写入落进 localStorage,刷新(重新读取)后还在', async () => {
    const store = memoryStorage()
    vi.stubGlobal('localStorage', store)
    resetState()

    const response = await sendChatMessage('午餐吃了200g米饭')
    await confirmMealEntry(confirmRequest(response.items[0]))

    expect(store.getItem('dietapp-demo-v1')).toContain('米饭')

    // 重新读一遍(等价于刷新页面重新挂载)
    const entries = await fetchTodayEntries()
    expect(entries.some((e) => e.food_name === '米饭')).toBe(true)

    vi.unstubAllGlobals()
  })

  it('localStorage 不可用时退化成内存,不让演示页崩掉', async () => {
    // Node 25 默认那个「有名字没方法」的 localStorage 就是这种情况
    vi.stubGlobal('localStorage', {} as Storage)
    resetState()

    const response = await sendChatMessage('午餐吃了200g米饭')
    await confirmMealEntry(confirmRequest(response.items[0]))
    const entries = await fetchTodayEntries()
    expect(entries.some((e) => e.food_name === '米饭')).toBe(true)

    vi.unstubAllGlobals()
  })
})
