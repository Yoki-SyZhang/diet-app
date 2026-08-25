// mock 版 /chat/messages/*,顶替 backend/app/routers/chat.py + services/chat_turn.py。
//
// 播报/总结文案刻意抄后端的确定性拼装口径(`_recognition_message_text`、
// `_fallback_recap_text`),这样演示看到的措辞就是真实 LLM 不可用时兜底的那一套,
// 不会给人「演示版文案更好看」的错觉。
//
// 意图判定是规则匹配,不是模型:够覆盖 new_entry / needs_clarification /
// edit_existing_entry / no_log_intent 四条分支,让状态机能被真的走一遍。

import type {
  ChatMessageOut,
  ChatTurnResponse,
  ConfirmableItem,
  ConfirmationPreview,
  Intent,
  ItemEstimateOutcome,
  MealSlot,
  ModifyCorrectionRequest,
  ModifyCorrectionResponse,
  OpenBatchOut,
  RecapRequest,
  RecapResponse,
} from '@/types/diet'
import { MEAL_SLOT_LABELS } from '@/types/diet'
import { attributionDate, fakeLatency, utcNowIso } from './attribution'
import {
  FALLBACK_PER_100,
  detectMealSlot,
  fallbackHit,
  findFoodDef,
  looksLikeEating,
  parseFoods,
  parseQuantity,
  scaleNutrients,
  type ParsedHit,
} from './foods'
import { loadState, mutate, type DemoState } from './store'

/** 对应后端 `format(x, 'g')`:200.0 显示成 200,12.5 保持 12.5。 */
function fmtNum(value: number): string {
  return String(Math.round(value * 100) / 100)
}

function newId(): string {
  const random = globalThis.crypto?.randomUUID?.()
  if (random) return random.replace(/-/g, '')
  return `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`
}

function appendMessage(
  state: DemoState,
  role: 'user' | 'assistant',
  content: string,
  extra: Partial<ChatMessageOut> = {},
  now: Date = new Date(),
): ChatMessageOut {
  const message: ChatMessageOut = {
    id: state.nextMessageId++,
    date: attributionDate(now),
    role,
    content,
    image_ref: null,
    created_at: utcNowIso(now),
    batch_id: null,
    kind: null,
    ...extra,
  }
  state.messages.push(message)
  return message
}

function toPreview(hit: ParsedHit, mealSlot: MealSlot): ConfirmationPreview {
  return {
    food_name: hit.item.food_name,
    quantity: hit.item.quantity,
    unit: 'g',
    meal_slot: mealSlot,
    nutrients: scaleNutrients(hit.per100, hit.item.quantity),
    source_tag: 'llm_estimate',
    confidence: hit.known ? 'high' : 'low',
    confidence_reason: hit.known
      ? '常见食物,按常规做法的通用口径估算'
      : '没匹配到常见食物,按名称粗略估算,建议改一下克重',
    warning: '可能不准',
  }
}

function toOutcome(hit: ParsedHit, mealSlot: MealSlot): ItemEstimateOutcome {
  return {
    parsed_item: hit.item,
    outcome: 'resolved',
    preview: toPreview(hit, mealSlot),
    message: null,
  }
}

/** 抄 `_recognition_message_text`:估算全成功时只有前半句。 */
function recognitionText(mealSlot: MealSlot, hits: ParsedHit[]): string {
  const foods = hits.map((hit) => `${hit.item.food_name} ${fmtNum(hit.item.quantity)}g`).join('、')
  return `我识别到了(${MEAL_SLOT_LABELS[mealSlot]}):${foods}。请在下方卡片里确认或修改。`
}

/** 抄 `_fallback_recap_text`。 */
function recapText(items: RecapRequest['items']): string {
  const confirmed = items.filter((item) => item.state === 'confirmed')
  const abandoned = items.filter((item) => item.state === 'abandoned')
  const parts: string[] = []
  if (confirmed.length > 0) {
    const foods = confirmed
      .map(
        (item) =>
          `${item.food_name}${fmtNum(item.quantity)}g` +
          (item.kcal !== null && item.kcal !== undefined ? `(约${fmtNum(item.kcal)}kcal)` : ''),
      )
      .join('、')
    parts.push(`已记录:${foods}。`)
  }
  if (abandoned.length > 0) {
    const foods = abandoned.map((item) => `${item.food_name}${fmtNum(item.quantity)}g`).join('、')
    parts.push(`已放弃:${foods}。`)
  }
  return `本轮处理完成。${parts.join('')}`
}

const VAGUE_QUANTITY_RE = /一些|一点|若干|随便|不知道多少|忘了多少|没称/
const EDIT_EXISTING_RE = /(删|去掉|改掉|撤销|改一下|修改).{0,6}(记录|明细|那条|那行|昨天)/

const CHITCHAT_REPLIES = [
  '收到~不过这句我没当成饮食记录。想记的话直接说吃了什么就行,比如「午餐吃了200g米饭」。',
  '好的!吃了什么随时告诉我,我帮你记进今日明细。',
  '明白啦。要记录的话说说食物和大概份量就行。',
]

/** POST /chat/messages */
export async function sendChatMessage(text: string): Promise<ChatTurnResponse> {
  await fakeLatency(700)
  const now = new Date()

  return mutate((state) => {
    const userMessage = appendMessage(state, 'user', text, {}, now)

    const reply = (
      content: string,
      intent: Intent,
      outcome: ChatTurnResponse['outcome'],
    ): ChatTurnResponse => ({
      user_message: userMessage,
      assistant_message: appendMessage(state, 'assistant', content, {}, now),
      intent,
      outcome,
      batch_id: null,
      items: [],
    })

    if (EDIT_EXISTING_RE.test(text)) {
      return reply(
        '已经写进今日明细的记录不能直接改:在上方明细里删掉那一行,再重新说一次就行。',
        'edit_existing_entry',
        null,
      )
    }

    let hits = parseFoods(text)
    if (hits.length === 0) {
      if (!looksLikeEating(text)) {
        const pick = CHITCHAT_REPLIES[state.messages.length % CHITCHAT_REPLIES.length]
        return reply(pick, 'no_log_intent', null)
      }
      hits = [fallbackHit(text)]
    }

    if (VAGUE_QUANTITY_RE.test(text)) {
      const names = hits.map((hit) => hit.item.food_name).join('、')
      return reply(
        `${names}大概吃了多少?给个克重或者份数我就能估了,比如「200g」「一碗」。`,
        'new_entry',
        'needs_clarification',
      )
    }

    const mealSlot = detectMealSlot(text, now)
    const batchId = newId()
    const items: ConfirmableItem[] = hits.map((hit) => ({
      confirmation_id: newId(),
      outcome: toOutcome(hit, mealSlot),
    }))

    const assistantMessage = appendMessage(
      state,
      'assistant',
      recognitionText(mealSlot, hits),
      { batch_id: batchId, kind: 'recognition' },
      now,
    )
    // 对应后端把完整快照写进 chat_message.food_summary_json:刷新后靠它重建卡片
    state.openBatches.push({ batch_id: batchId, items })

    return {
      user_message: userMessage,
      assistant_message: assistantMessage,
      intent: 'new_entry' as Intent,
      outcome: 'resolved' as const,
      batch_id: batchId,
      items,
    }
  }, now)
}

/** POST /chat/messages/modify —— 全程不写 chat_message,和后端一致。 */
export async function sendModifyCorrection(
  request: ModifyCorrectionRequest,
): Promise<ModifyCorrectionResponse> {
  await fakeLatency(600)
  const { confirmation_id, original_item, meal_slot, correction_text } = request

  const newFoods = parseFoods(correction_text)
  if (newFoods.length > 1) {
    return {
      confirmation_id,
      success: false,
      outcome: null,
      failure_reason: `修正结果不明确(解析出 ${newFoods.length} 项食物),请重新描述`,
    }
  }

  let hit: ParsedHit
  if (newFoods.length === 1) {
    // 换了食物:「其实是蛋炒饭」。没说新份量时沿用原来的克重。
    hit = newFoods[0]
    if (!/\d|[一两二三四五六七八九十半]/.test(correction_text)) {
      hit = { ...hit, item: { ...hit.item, quantity: original_item.quantity } }
    }
  } else {
    // 只改份量:「改成200g」。食物名沿用原来的。
    const grams = parseQuantity(correction_text, original_item.food_name)
    if (grams === null) {
      return {
        confirmation_id,
        success: false,
        outcome: null,
        failure_reason: '没能把这句话理解成对这项食物的修正,请重新描述',
      }
    }
    const def = findFoodDef(original_item.food_name)
    hit = {
      item: { ...original_item, quantity: grams },
      per100: def?.per100 ?? FALLBACK_PER_100,
      known: def !== null,
    }
  }

  return {
    confirmation_id,
    success: true,
    outcome: toOutcome(hit, meal_slot),
    failure_reason: null,
  }
}

/** POST /chat/messages/recap —— 整批收尾时调一次,并清掉未完成快照。 */
export async function sendRecap(request: RecapRequest): Promise<RecapResponse> {
  await fakeLatency(400)
  const now = new Date()
  return mutate((state) => {
    state.openBatches = state.openBatches.filter((batch) => batch.batch_id !== request.batch_id)
    const message = appendMessage(
      state,
      'assistant',
      recapText(request.items),
      { batch_id: request.batch_id, kind: 'recap' },
      now,
    )
    return { assistant_message: message }
  }, now)
}

/** GET /chat/messages/today */
export async function fetchTodayMessages(): Promise<ChatMessageOut[]> {
  const now = new Date()
  const today = attributionDate(now)
  return loadState(now)
    .messages.filter((message) => message.date === today)
    .sort((a, b) => a.id - b.id)
}

/** GET /chat/messages/open-batch —— 判定逻辑逐条对应 find_open_batch()。 */
export async function fetchOpenBatch(): Promise<OpenBatchOut | null> {
  const now = new Date()
  const today = attributionDate(now)
  const state = loadState(now)
  const messages = state.messages.filter((message) => message.date === today)

  const recognition = [...messages].reverse().find((message) => message.kind === 'recognition')
  if (!recognition?.batch_id) return null
  // 同批已有 recap → 正常收尾过了,不打扰
  if (messages.some((m) => m.kind === 'recap' && m.batch_id === recognition.batch_id)) return null

  const snapshot = state.openBatches.find((batch) => batch.batch_id === recognition.batch_id)
  if (!snapshot) return null

  const written = new Set(
    state.entries.filter((entry) => entry.date === today).map((entry) => entry.confirmation_id),
  )
  const remaining = snapshot.items.filter((item) => !written.has(item.confirmation_id))
  // 快照里每项都已写进今日明细 → 只是 recap 没送达,数据其实是完整的
  if (remaining.length === 0) return null
  return { batch_id: snapshot.batch_id, items: remaining }
}
