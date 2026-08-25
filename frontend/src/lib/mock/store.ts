// mock 后端的「数据库」:整份状态一个 JSON,存在访问者自己的 localStorage 里。
// 不同访问者互不共享,也不会有任何数据离开浏览器。
//
// 结构对应真实后端的两张表 + 批次追踪三列:
//   messages ↔ chat_message(含 batch_id / kind / food_summary_json 快照)
//   entries  ↔ meal_entry(含 confirmation_id 幂等键)
// 归属日过滤放在读取处,和 list_today_* 一样。

import type { ChatMessageOut, ConfirmableItem, MealEntryOut } from '@/types/diet'
import { attributionDate } from './attribution'

const STORAGE_KEY = 'dietapp-demo-v1'

export interface DemoState {
  /** 种子数据是哪个归属日建的;跨天再打开就重新播种,演示永远是「今天」 */
  seededDate: string
  messages: ChatMessageOut[]
  entries: MealEntryOut[]
  /** 识别过、但整批还没收尾的快照;对应 find_open_batch 读的 food_summary_json */
  openBatches: { batch_id: string; items: ConfirmableItem[] }[]
  nextMessageId: number
  nextEntryId: number
}

// 无痕模式 / 禁用站点数据时 localStorage 会直接抛异常。那种情况下退化成进程内内存,
// 演示照样能玩通,只是刷新后回到种子状态。
let memoryFallback: DemoState | null = null

/** 取一个**真的能用**的 Storage。
 *
 *  不直接用 `globalThis.localStorage`:Node 自带的实验性 localStorage 在没给
 *  `--localstorage-file` 时会占着这个名字但方法不可用(vitest 里就是这样,会把
 *  jsdom 那个真的挡住)。所以这里认方法不认名字,顺带覆盖掉无痕模式抛异常的情况。 */
export function storage(): Storage | null {
  try {
    const candidate = globalThis.window?.localStorage ?? globalThis.localStorage
    return typeof candidate?.getItem === 'function' ? candidate : null
  } catch {
    return null
  }
}

function readRaw(): string | null {
  try {
    return storage()?.getItem(STORAGE_KEY) ?? null
  } catch {
    return null
  }
}

function writeRaw(value: string): void {
  try {
    storage()?.setItem(STORAGE_KEY, value)
  } catch {
    /* 存不进去(配额满/无痕)就只留内存副本 */
  }
}

export function seedState(now: Date = new Date()): DemoState {
  const date = attributionDate(now)
  const createdAt = now.toISOString()
  const message = (
    id: number,
    role: 'user' | 'assistant',
    content: string,
    extra: Partial<ChatMessageOut> = {},
  ): ChatMessageOut => ({
    id,
    date,
    role,
    content,
    image_ref: null,
    created_at: createdAt,
    batch_id: null,
    kind: null,
    ...extra,
  })

  // 种子批次是「已收尾」的:识别播报 + 总结都在,两条明细也已写入,
  // 所以 findOpenBatch 不会在首次打开时弹「继续上次」——那对新访客只是噪声。
  const seedBatch = 'seed-batch'
  return {
    seededDate: date,
    nextMessageId: 5,
    nextEntryId: 3,
    openBatches: [],
    messages: [
      message(
        1,
        'assistant',
        '这是 Mock 演示模式:所有数据只存在你自己的浏览器里,不会上传,也不会调用真实模型。' +
          '直接描述你吃了什么试试,比如「午餐吃了200g米饭和一份西兰花」。',
      ),
      message(2, 'user', '早餐吃了两个水煮蛋和一杯牛奶'),
      message(
        3,
        'assistant',
        '我识别到了(早餐):水煮蛋 100g、牛奶 250g。请在下方卡片里确认或修改。',
        { batch_id: seedBatch, kind: 'recognition' },
      ),
      message(4, 'assistant', '本轮处理完成。已记录:水煮蛋100g(约147kcal)、牛奶250g(约135kcal)。', {
        batch_id: seedBatch,
        kind: 'recap',
      }),
    ],
    entries: [
      {
        id: 1,
        confirmation_id: 'seed-egg',
        date,
        meal_slot: 'breakfast',
        food_name: '水煮蛋',
        quantity: 100,
        unit: 'g',
        kcal: 147,
        carb_g: 1.1,
        protein_g: 12.6,
        fat_g: 10,
        fiber_g: null,
        source_tag: 'llm_estimate',
        created_at: createdAt,
      },
      {
        id: 2,
        confirmation_id: 'seed-milk',
        date,
        meal_slot: 'breakfast',
        food_name: '牛奶',
        quantity: 250,
        unit: 'g',
        kcal: 135,
        carb_g: 8.5,
        protein_g: 7.5,
        fat_g: 8,
        fiber_g: 0,
        source_tag: 'llm_estimate',
        created_at: createdAt,
      },
    ],
  }
}

function isDemoState(value: unknown): value is DemoState {
  if (typeof value !== 'object' || value === null) return false
  const state = value as Partial<DemoState>
  return (
    typeof state.seededDate === 'string' &&
    Array.isArray(state.messages) &&
    Array.isArray(state.entries) &&
    Array.isArray(state.openBatches) &&
    typeof state.nextMessageId === 'number' &&
    typeof state.nextEntryId === 'number'
  )
}

export function loadState(now: Date = new Date()): DemoState {
  const raw = readRaw()
  if (raw !== null) {
    try {
      const parsed: unknown = JSON.parse(raw)
      // 跨天重新播种:对话历史只保留当前归属日(SPEC / ADR 0006),
      // 隔天再来看到的是一份新鲜的今天,而不是空页面。
      if (isDemoState(parsed) && parsed.seededDate === attributionDate(now)) {
        memoryFallback = parsed
        return parsed
      }
    } catch {
      /* 存坏了就重新播种,不让演示页因此白屏 */
    }
  }
  if (memoryFallback !== null && memoryFallback.seededDate === attributionDate(now)) {
    return memoryFallback
  }
  const fresh = seedState(now)
  saveState(fresh)
  return fresh
}

export function saveState(state: DemoState): void {
  memoryFallback = state
  writeRaw(JSON.stringify(state))
}

/** 读-改-写 一步完成,省得每个调用点都记得存回去。 */
export function mutate<T>(fn: (state: DemoState) => T, now: Date = new Date()): T {
  const state = loadState(now)
  const result = fn(state)
  saveState(state)
  return result
}

/** 「重置演示数据」按钮走这里:清干净再播一份新种子。 */
export function resetState(now: Date = new Date()): DemoState {
  try {
    storage()?.removeItem(STORAGE_KEY)
  } catch {
    /* ignore */
  }
  memoryFallback = null
  const fresh = seedState(now)
  saveState(fresh)
  return fresh
}
