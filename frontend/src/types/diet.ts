// 1.9 前后端契约类型(镜像 backend/app/schemas/{chat,meal_entry,diet_parse,food_estimate}.py)
// + RecordTab 状态机的纯前端类型(tasks/current.md"五、前端组件实现")。

export type MealSlot = 'breakfast' | 'lunch' | 'dinner' | 'other'
export type PreparationState = 'raw' | 'cooked' | 'ready_to_consume'
export type LlmOutcome =
  | 'resolved'
  | 'needs_clarification'
  | 'service_unavailable'
  | 'invalid_model_output'
export type Intent = 'new_entry' | 'correct_pending_item' | 'edit_existing_entry' | 'no_log_intent'
export type SourceTag = 'chn_table' | 'usda' | 'decompose_estimate' | 'llm_estimate' | 'user_create'
export type Confidence = 'low' | 'medium' | 'high'

export interface ParsedFoodItem {
  food_name: string
  quantity: number
  unit: 'g'
  preparation_state: PreparationState
}

export interface NutrientSet {
  kcal: number | null
  carb_g: number | null
  protein_g: number | null
  fat_g: number | null
  fiber_g: number | null
}

export interface ConfirmationPreview {
  food_name: string
  quantity: number
  unit: 'g'
  meal_slot: MealSlot
  nutrients: NutrientSet
  source_tag: SourceTag
  confidence: Confidence
  confidence_reason: string
  warning: '可能不准'
}

export interface ItemEstimateOutcome {
  parsed_item: ParsedFoodItem
  outcome: LlmOutcome
  preview: ConfirmationPreview | null
  message: string | null
}

export interface ConfirmableItem {
  confirmation_id: string
  outcome: ItemEstimateOutcome
}

export interface ChatMessageOut {
  id: number
  date: string
  role: 'user' | 'assistant'
  content: string
  image_ref: string | null
  created_at: string
  batch_id: string | null
  kind: 'recognition' | 'recap' | null
}

export interface ChatTurnResponse {
  user_message: ChatMessageOut
  assistant_message: ChatMessageOut
  intent: Intent
  outcome: LlmOutcome | null
  batch_id: string | null
  items: ConfirmableItem[]
}

export interface ModifyCorrectionRequest {
  confirmation_id: string
  original_item: ParsedFoodItem
  meal_slot: MealSlot
  correction_text: string
}

export interface ModifyCorrectionResponse {
  confirmation_id: string
  success: boolean
  outcome: ItemEstimateOutcome | null
  failure_reason: string | null
}

export interface BatchItemStatus {
  food_name: string
  quantity: number
  state: 'confirmed' | 'abandoned'
  kcal?: number | null
}

export interface RecapRequest {
  batch_id: string
  meal_slot: MealSlot
  items: BatchItemStatus[]
  now_utc: string
}

export interface RecapResponse {
  assistant_message: ChatMessageOut
}

export interface OpenBatchOut {
  batch_id: string
  items: ConfirmableItem[]
}

export interface ConfirmMealEntryRequest {
  confirmation_id: string
  preview: ConfirmationPreview
  now_utc: string
}

export interface MealEntryOut {
  id: number
  confirmation_id: string
  date: string
  meal_slot: MealSlot
  food_name: string
  quantity: number
  unit: 'g' | 'serving'
  kcal: number | null
  carb_g: number | null
  protein_g: number | null
  fat_g: number | null
  fiber_g: number | null
  source_tag: SourceTag
  created_at: string
}

/** GET /today。当前归属日(SPEC §6.1);1.11/1.12 的 kcal 目标 / 今日 Δ 以后加在这里。 */
export interface TodayOut {
  date: string
}

// ---------------------------------------------------------------------------
// RecordTab 状态机(纯前端,不出现在 API 里)
// ---------------------------------------------------------------------------

export type ItemUiState =
  | 'pending'
  | 'to_confirm'
  | 'to_modify'
  | 'to_reparse'
  | 'modifying'
  | 'confirmed'
  | 'abandoned'

export interface PendingItem {
  clientItemId: string
  /** 后端签发,原样携带,贯穿整个生命周期(包括修改后) */
  confirmationId: string
  /** 当前预览值 */
  outcome: ItemEstimateOutcome
  uiState: ItemUiState
  /** confirmed 后记录,仅展示用 */
  writtenEntryId: number | null
  /** to_reparse 时暂存的修正文本(也是"修改:…"留痕的来源) */
  pendingModifyNote: string | null
  modifyError: string | null
  /** 顶部批量提交这一项失败时的提示 */
  writeError: string | null
}

export const TERMINAL_STATES: ReadonlySet<ItemUiState> = new Set(['confirmed', 'abandoned'])

export const MEAL_SLOT_LABELS: Record<MealSlot, string> = {
  breakfast: '早餐',
  lunch: '午餐',
  dinner: '晚餐',
  other: '其他',
}

export const PREP_STATE_LABELS: Record<PreparationState, string> = {
  raw: '生',
  cooked: '熟',
  ready_to_consume: '即食',
}
